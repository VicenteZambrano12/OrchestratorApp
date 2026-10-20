"""Coordinate routine classification, requirement collection, previews, and saves.

The workflow loads user-scoped session state and database context, asks a
stage-specific generator to classify the query, and validates structured output
before branching. Missing requirements produce follow-up questions rather than
invented prescriptions. Generated plans are checked against the catalog and
requested edit; invalid structured generations receive up to two repair attempts.

Previews are cached with unique draft IDs and require explicit confirmation.
Saving bypasses LLM generation, persists a new active version idempotently, or
returns a client-save request when configured. This module selects stages and
payloads; its generator dependency owns system prompts and provider invocation.
"""

from collections.abc import Callable, Mapping
from typing import Literal, Protocol
from uuid import uuid4

from pydantic import ValidationError

from obervability.logger import Logger
from utils.routinemaker.dataclass.models import (
    RoutineChange, RoutineMakerResult, RoutineParameters, RoutinePlan,
    RoutineState, _RoutingDecision,
)
from utils.routinemaker.func.repository import RoutineInputError, RoutineRepository
from utils.pipeline.progress import report_progress


logger = Logger.get_logger(__name__)


class RoutineStore(Protocol):
    """Specify the session-and-user-scoped workflow persistence boundary.

    Implementations own storage state; this protocol declares no attributes.
    Cached values are JSON representations of RoutineState and are separate
    from conversation turns.
    """

    def get_routine_state(self, session_id: str, user_id: int) -> str | None:
        """Read a user's cached workflow within a session.

        Args:
            session_id: Caller-supplied session identifier.
            user_id: Database user identifier qualifying the cached state.

        Returns:
            str | None: Serialized RoutineState, or None when absent.
        """
        ...

    def set_routine_state(self, session_id: str, user_id: int, state: str) -> None:
        """Replace a user's cached workflow within a session.

        Args:
            session_id: Caller-supplied session identifier.
            user_id: Database user identifier qualifying the cached state.
            state: Serialized RoutineState supplied by the workflow.

        Returns:
            None: Persists state through the concrete store implementation.
        """
        ...


@Logger.trace(logger)
def save_draft(
    *,
    repository: RoutineRepository,
    state_store: RoutineStore,
    session_id: str,
    user_id: int,
    language: str = "EN",
    draft_id: str | None = None,
    defer_save: bool = False,
    routine: RoutinePlan | None = None,
) -> RoutineMakerResult:
    """Confirm the current cached preview without invoking a language model.

    Args:
        repository: Database boundary for user validation and versioned saves.
        state_store: Session-and-user-scoped serialized workflow store.
        session_id: Nonblank session identifier.
        user_id: Existing positive database user identifier.
        language: ``EN`` or ``ES`` for outcome messages.
        draft_id: Optional identity guard against stale preview confirmations.
        defer_save: Return ``save_requested`` without database or cache writes.
        routine: Optional plan equality guard against modified client payloads.

    Returns:
        RoutineMakerResult: ``needs_routine`` when no confirmable draft exists,
            ``save_requested`` when persistence is deferred, or ``saved`` with
            the existing or newly persisted version ID.

    Raises:
        RoutineInputError: Session, language, user, draft identity, or submitted
            plan does not satisfy confirmation requirements.
        ValidationError: Cached workflow state is invalid.
        ValueError: The repository rejects the plan.
        RoutineDataError: A stored idempotent version has an invalid identifier.
        RuntimeError: The repository cannot obtain a newly saved identifier.
        sqlite3.Error: Local database operations fail.
        psycopg.Error: Cloud database operations fail.
    """
    # 1. Validate confirmation scope before reading or persisting user-owned plans.
    if not isinstance(session_id, str) or not session_id.strip():
        raise RoutineInputError("Routine requests require a session_id.")
    if language not in ("EN", "ES"):
        raise RoutineInputError("language must be EN or ES")
    repository.validate_user(user_id)
    # 2. Bind confirmation to the server-cached draft rather than client plan contents.
    cached = state_store.get_routine_state(session_id, user_id)
    state = RoutineState.model_validate_json(cached) if cached else RoutineState()
    if draft_id is not None and draft_id != state.draft_id:
        raise RoutineInputError("This draft is no longer available. Review the latest routine preview.")
    if routine is not None and routine != state.routine:
        raise RoutineInputError("The submitted routine does not match the latest routine preview.")
    # 3. Preserve idempotent retries while rejecting absent or unconfirmable previews.
    already_saved = draft_id is not None and state.saved_routine_id is not None
    if (
        (not state.awaiting_confirmation and not already_saved)
        or state.routine is None or state.draft_id is None
    ):
        logger.info("Routine confirmation outcome=needs_routine")
        return RoutineMakerResult(
            "needs_routine", state.parameters,
            "No hay un borrador pendiente de confirmar. Genera o modifica una rutina primero."
            if language == "ES" else
            "There is no draft awaiting confirmation. Generate or modify a routine first.",
            state.routine,
        )
    # 4. Let capable clients own persistence without claiming a completed save.
    if defer_save:
        logger.info("Routine confirmation outcome=save_requested")
        return RoutineMakerResult(
            "save_requested", state.parameters,
            "Guardando la rutina confirmada."
            if language == "ES" else "Saving the confirmed routine.",
            state.routine, draft_id=state.draft_id,
        )
    # 5. Persist a new version once, then cache its identity for later retries.
    if not already_saved:
        report_progress("routine_save", "Saving your confirmed routine")
        state.saved_routine_id = repository.save(
            user_id, state.routine, state.parameters, state.draft_id, state.source_routine_id,
        )
        state.awaiting_confirmation = False
        state_store.set_routine_state(session_id, user_id, state.model_dump_json())
    logger.info("Routine confirmation outcome=saved reused=%s", already_saved)
    return RoutineMakerResult(
        "saved", state.parameters,
        "Guardada como una nueva version y seleccionada como tu rutina actual."
        if language == "ES" else
        "Saved as a new version and selected as your current routine.",
        state.routine, state.saved_routine_id,
    )


def handle(
    generate_response: Callable[[str, dict[str, object]], str],
    query: str,
    *,
    repository: RoutineRepository,
    state_store: RoutineStore,
    session_id: str,
    user_id: int,
    parameters: RoutineParameters | Mapping[str, object] | None = None,
    routine: RoutinePlan | None = None,
    language: str = "EN",
    client_saves_routine: bool = False,
) -> RoutineMakerResult:
    """Advance a routine workflow from query classification to preview or save.

    Args:
        generate_response: Stage-and-payload callback that invokes the configured
            LLM with the corresponding system instructions.
        query: Nonblank user message, preserved in workflow request history.
        repository: User, routine, exercise catalog, and persistence boundary.
        state_store: Serialized workflow store scoped by session and user.
        session_id: Nonblank caller-supplied session identifier.
        user_id: Existing positive database user identifier.
        parameters: Optional validated requirements or mapping replacing cached
            requirements before classification.
        routine: Optional plan replacing the cached plan before classification.
        language: ``EN`` or ``ES`` for follow-ups and outcome messages.
        client_saves_routine: Defer confirmed persistence to the client.

    Returns:
        RoutineMakerResult: Typed outcome carrying collected requirements,
            localized feedback, and any preview or saved-version identifiers.

    Raises:
        RoutineInputError: Query scope or selected user-owned routine is invalid.
        ValidationError: Cached, supplied, or routed data remains invalid after
            applicable structured-output retries.
        ValueError: Generated plans or edit constraints remain invalid after
            three attempts, or required database data is invalid.
        Exception: Generation, state-store, and database failures propagate
            without being converted to no-match results.
    """
    # 1. Validate request scope and load only this user's session workflow.
    if not isinstance(query, str) or not query.strip():
        raise RoutineInputError("query must be a non-empty string")
    if language not in ("EN", "ES"):
        raise RoutineInputError("language must be EN or ES")
    if not isinstance(session_id, str) or not session_id.strip():
        raise RoutineInputError("Routine requests require a session_id.")
    report_progress("routine_context", "Loading your routine and exercise data")
    repository.validate_user(user_id)
    cached = state_store.get_routine_state(session_id, user_id)
    state = RoutineState.model_validate_json(cached) if cached else RoutineState()
    if parameters is not None:
        state.parameters = RoutineParameters.model_validate(parameters)
    if routine is not None:
        state.routine = RoutinePlan.model_validate(routine)
    # 2. Ground LLM classification in saved routines, requirements, and catalog data.
    payload: dict[str, object] = {
        "query": query, "language": language, **state.model_dump(),
        "saved_routines": repository.routines(user_id),
        "exercises": repository.catalog(state.parameters),
    }
    report_progress("routine_routing", "Choosing the next routine action")
    # 3. Repair schema-invalid routing output without hiding provider failures.
    for attempt in range(3):
        response = generate_response("routing", payload)
        try:
            decision = _RoutingDecision.model_validate_json(response)
            break
        except ValidationError as error:
            logger.warning("Routine routing decision rejected attempt=%d max_attempts=3", attempt + 1)
            if attempt == 2:
                raise
            payload["validation_error"] = str(error)
    payload.pop("validation_error", None)
    logger.debug("Routine action selected intent=%s", decision.intent)

    def result(
        status: Literal["needs_parameters", "needs_changes", "needs_routine", "awaiting_confirmation", "saved", "no_match"],
        message: str, *, persist: bool = True,
    ) -> RoutineMakerResult:
        """Package a workflow outcome and optionally persist its current state.

        Args:
            status: Outcome selected by this workflow branch.
            message: Localized explanation or follow-up question.
            persist: Whether to replace the cached state before returning.

        Returns:
            RoutineMakerResult: Current requirements and plan, with identifiers
                included only for the corresponding outcome.

        Raises:
            Exception: Cache persistence failures propagate to the caller.
        """
        # 1. Keep cache updates and response identifiers consistent across branches.
        if persist:
            state_store.set_routine_state(session_id, user_id, state.model_dump_json())
        return RoutineMakerResult(
            status, state.parameters, message, state.routine,
            state.saved_routine_id if status == "saved" else None,
            state.draft_id if status == "awaiting_confirmation" else None,
        )

    def localized(en: str, es: str) -> str:
        """Select workflow feedback using the validated request language.

        Args:
            en: English message.
            es: Spanish message.

        Returns:
            str: Spanish text for ES, otherwise English text.
        """
        # 1. Localize deterministic workflow feedback without another LLM call.
        return es if language == "ES" else en

    # 4. Keep unsupported requests read-only and confirmations independent of generation.
    if decision.intent == "no_match":
        return result("no_match", decision.message.strip(), persist=False)
    if decision.intent == "save":
        return save_draft(
            repository=repository, state_store=state_store,
            session_id=session_id, user_id=user_id, language=language,
            defer_save=client_saves_routine,
        )

    # 5. Establish creation or edit context without guessing ambiguous saved versions.
    loaded_parameters: RoutineParameters | None = None
    if decision.intent == "create":
        if decision.start_new or state.routine is not None:
            state = RoutineState()
        state.workflow = "create"
    elif decision.intent == "update_saved":
        selected = decision.routine_id
        choices = repository.routines(user_id)
        if selected is None and state.workflow == "update_saved" and state.saved_routine_id is None:
            selected = state.source_routine_id
        if selected is None:
            current = [row for row in choices if row["is_active"]]
            if len(current) == 1:
                selected = current[0]["id"]
        if selected is None and len(choices) == 1:
            only_id = choices[0]["id"]
            if not isinstance(only_id, int):
                raise ValueError("Saved routine IDs must be integers.")
            selected = only_id
        if selected is None:
            if state.workflow != "update_saved" or state.source_routine_id is not None:
                state = RoutineState(workflow="update_saved")
            state.selection_parameters.update(decision.parameters.model_dump(exclude_unset=True))
            state.parameters = RoutineParameters.model_validate(state.selection_parameters)
            state.change = RoutineChange.model_validate({
                **state.change.model_dump(), **decision.change.model_dump(exclude_unset=True),
            })
            state.requests.append(query)
            if not choices:
                return result("needs_routine", localized(
                    "You have no saved routines to modify. Create a routine first.",
                    "No tienes rutinas guardadas para modificar. Crea una rutina primero.",
                ))
            return result("needs_routine", localized(
                "Which saved routine should I modify? Choose by name, or say the most recent or an older version. Available, newest first:\n",
                "Que rutina guardada quieres modificar? Elige por nombre o indica la version mas reciente o una anterior. Disponibles, de mas reciente a mas antigua:\n",
            ) + "\n".join(f"- {choice['name']}" for choice in choices))
        if state.workflow != "update_saved" or state.source_routine_id != selected:
            plan, known = repository.load(user_id, selected)
            loaded_parameters = known
            pending_selection = state.workflow == "update_saved" and state.source_routine_id is None
            state = RoutineState(
                parameters=RoutineParameters.model_validate({
                    **known.model_dump(), **(state.selection_parameters if pending_selection else {}),
                }),
                routine=plan, source_routine_id=selected,
                change=state.change if pending_selection else RoutineChange(),
                requests=state.requests if pending_selection else [],
            )
        state.workflow = "update_saved"
    else:
        if state.routine is None or state.draft_id is None or state.saved_routine_id is not None:
            return result("needs_routine", localized(
                "There is no unsaved draft to modify. Create one or select a saved routine.",
                "No hay un borrador sin guardar. Crea uno o selecciona una rutina guardada.",
            ), persist=False)
        state.workflow = "update_draft"

    # 6. Merge extracted requirements and revoke confirmation whenever an edit begins.
    previous_parameters = state.parameters if loaded_parameters is None else loaded_parameters
    state.parameters = RoutineParameters.model_validate({
        **state.parameters.model_dump(),
        **decision.parameters.model_dump(exclude_unset=True),
    })
    state.change = RoutineChange.model_validate({
        **state.change.model_dump(),
        **decision.change.model_dump(exclude_unset=True),
    })
    state.requests.append(query)
    state.awaiting_confirmation = False
    state.saved_routine_id = None
    payload.update(state.model_dump())
    payload["intent"] = state.workflow
    # 7. Ask for missing requirements instead of generating an under-specified plan.
    if state.parameters.missing_fields:
        payload["missing_parameters"] = list(state.parameters.missing_fields)
        return result("needs_parameters", generate_response("parameters", payload))

    # 8. Ground generation and edit targets in the level-appropriate exercise catalog.
    catalog = repository.catalog(state.parameters)
    payload["exercises"] = catalog
    payload["routine_schema"] = RoutinePlan.model_json_schema()
    parameters_changed = state.parameters != previous_parameters
    if state.workflow != "create":
        missing = state.change.missing_fields if state.change.action is not None or not parameters_changed else []
        if missing:
            payload["missing_changes"] = missing
            return result("needs_changes", generate_response("parameters", payload))
        change = state.change
        if state.routine is None:
            raise ValueError("An update requires a routine.")
        day = next((day for day in state.routine.days if day.day == change.day), None)
        valid_ids = {row["id"] for row in catalog}
        if change.action is not None and (
            day is None or change.exercise_id not in valid_ids
            or (change.action != "add" and change.exercise_id not in {
                exercise.exercise_id for exercise in day.exercises
            })
            or (change.action == "add" and change.exercise_id in {
                exercise.exercise_id for exercise in day.exercises
            })
            or (change.action == "replace" and change.replacement_exercise_id not in valid_ids)
            or (change.action == "remove" and len(day.exercises) == 1)
        ):
            return result("needs_changes", localized(
                "Select a training day and an exercise by name. Remove, replace or adjust an exercise in that day; a training day must keep at least one exercise.",
                "Elige un dia de entrenamiento y un ejercicio por su nombre. Quita, sustituye o ajusta un ejercicio de ese dia; cada dia debe mantener al menos un ejercicio.",
            ))

    # 9. Validate generated prescriptions and retry only rejected plan/edit output.
    stage = "routine_maker" if state.workflow == "create" else "routine_updater"
    report_progress("routine_build" if stage == "routine_maker" else stage, "Building your routine preview" if stage == "routine_maker" else "Updating your routine preview")
    for attempt in range(3):
        response = generate_response(stage, payload)
        try:
            generated = RoutinePlan.model_validate_json(
                response, context={
                    "parameters": state.parameters, "catalog": catalog, "require_summary": True,
                },
            )
            if state.workflow != "create" and state.routine is not None and state.change.action is not None:
                _validate_change(state.routine, generated, state.change)
            break
        except ValueError as error:
            logger.warning(
                "Routine plan rejected stage=%s attempt=%d max_attempts=3",
                stage, attempt + 1,
            )
            if attempt == 2:
                raise
            payload["validation_error"] = str(error)
    # 10. Cache a fresh preview identity; database persistence still needs confirmation.
    state.routine = generated
    state.awaiting_confirmation = True
    state.draft_id = str(uuid4())
    state.change = RoutineChange()
    return result("awaiting_confirmation", localized(
        "Here is your draft. It has not been saved. Would you like to save it, or change any exercises?",
        "Este es tu borrador. No se ha guardado. Quieres guardarlo o cambiar algun ejercicio?",
    ))


def _validate_change(previous: RoutinePlan, updated: RoutinePlan, change: RoutineChange) -> None:
    """Reject generated exercise changes outside the explicitly requested edit.

    Args:
        previous: Plan before the requested change.
        updated: Generated replacement plan.
        change: Validated action and target identifiers.

    Returns:
        None: Accepts the updated plan when targeted exercise constraints hold.

    Raises:
        ValueError: Required IDs are absent, day counts differ, unaffected
            exercises change, or the requested operation was not applied.
    """
    # 1. Require a concrete target and preserve the original number of training days.
    exercise_id = change.exercise_id
    if exercise_id is None:
        raise ValueError("An exercise edit requires an exercise ID.")
    if len(previous.days) != len(updated.days):
        raise ValueError("An exercise edit must preserve the other training days.")
    # 2. Compare exercise lists so model output cannot introduce unrelated edits.
    for before, after in zip(previous.days, updated.days):
        if before.day != change.day:
            if before.exercises != after.exercises:
                raise ValueError("Preserve exercises on unaffected days.")
            continue
        expected = [exercise.exercise_id for exercise in before.exercises]
        actual = [exercise.exercise_id for exercise in after.exercises]
        if change.action == "remove":
            expected.remove(exercise_id)
        elif change.action == "replace":
            if change.replacement_exercise_id is None:
                raise ValueError("A replacement requires a replacement exercise ID.")
            expected[expected.index(exercise_id)] = change.replacement_exercise_id
        elif change.action == "add":
            if change.exercise_id not in actual:
                raise ValueError("The requested exercise was not added.")
            expected = [exercise.exercise_id for exercise in before.exercises]
            actual = [exercise_id for exercise_id in actual if exercise_id != change.exercise_id]
        if expected != actual:
            raise ValueError("Apply only the requested exercise change, preserving order.")
        for exercise in before.exercises:
            if exercise.exercise_id == change.exercise_id and change.action != "add":
                if change.action == "adjust":
                    adjusted = next(item for item in after.exercises if item.exercise_id == exercise.exercise_id)
                    if adjusted == exercise:
                        raise ValueError("The requested exercise adjustment was not applied.")
                continue
            if exercise not in after.exercises:
                raise ValueError("Preserve prescriptions for unaffected exercises.")
