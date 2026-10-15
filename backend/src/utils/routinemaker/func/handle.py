from collections.abc import Callable, Mapping
from typing import Literal, Protocol
from uuid import uuid4

from pydantic import ValidationError

from utils.routinemaker.dataclass.models import (
    RoutineChange, RoutineMakerResult, RoutineParameters, RoutinePlan,
    RoutineState, _RoutingDecision,
)
from utils.routinemaker.func.repository import RoutineInputError, RoutineRepository
from utils.pipeline.progress import report_progress


class RoutineStore(Protocol):
    def get_routine_state(self, session_id: str, user_id: int) -> str | None: ...

    def set_routine_state(self, session_id: str, user_id: int, state: str) -> None: ...


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
    """Persist the cached preview without invoking a model."""
    if not isinstance(session_id, str) or not session_id.strip():
        raise RoutineInputError("Routine requests require a session_id.")
    if language not in ("EN", "ES"):
        raise RoutineInputError("language must be EN or ES")
    repository.validate_user(user_id)
    cached = state_store.get_routine_state(session_id, user_id)
    state = RoutineState.model_validate_json(cached) if cached else RoutineState()
    if draft_id is not None and draft_id != state.draft_id:
        raise RoutineInputError("This draft is no longer available. Review the latest routine preview.")
    if routine is not None and routine != state.routine:
        raise RoutineInputError("The submitted routine does not match the latest routine preview.")
    already_saved = draft_id is not None and state.saved_routine_id is not None
    if (
        (not state.awaiting_confirmation and not already_saved)
        or state.routine is None or state.draft_id is None
    ):
        return RoutineMakerResult(
            "needs_routine", state.parameters,
            "No hay un borrador pendiente de confirmar. Genera o modifica una rutina primero."
            if language == "ES" else
            "There is no draft awaiting confirmation. Generate or modify a routine first.",
            state.routine,
        )
    if defer_save:
        return RoutineMakerResult(
            "save_requested", state.parameters,
            "Guardando la rutina confirmada."
            if language == "ES" else "Saving the confirmed routine.",
            state.routine, draft_id=state.draft_id,
        )
    if not already_saved:
        report_progress("routine_save", "Saving your confirmed routine")
        state.saved_routine_id = repository.save(
            user_id, state.routine, state.parameters, state.draft_id, state.source_routine_id,
        )
        state.awaiting_confirmation = False
        state_store.set_routine_state(session_id, user_id, state.model_dump_json())
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
    """Classify first, validate, collect requirements, then preview or confirm a save."""
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
    payload: dict[str, object] = {
        "query": query, "language": language, **state.model_dump(),
        "saved_routines": repository.routines(user_id),
        "exercises": repository.catalog(state.parameters),
    }
    report_progress("routine_routing", "Choosing the next routine action")
    for attempt in range(3):
        response = generate_response("routing", payload)
        try:
            decision = _RoutingDecision.model_validate_json(response)
            break
        except ValidationError as error:
            if attempt == 2:
                raise
            payload["validation_error"] = str(error)
    payload.pop("validation_error", None)

    def result(
        status: Literal["needs_parameters", "needs_changes", "needs_routine", "awaiting_confirmation", "saved", "no_match"],
        message: str, *, persist: bool = True,
    ) -> RoutineMakerResult:
        if persist:
            state_store.set_routine_state(session_id, user_id, state.model_dump_json())
        return RoutineMakerResult(
            status, state.parameters, message, state.routine,
            state.saved_routine_id if status == "saved" else None,
            state.draft_id if status == "awaiting_confirmation" else None,
        )

    def localized(en: str, es: str) -> str:
        return es if language == "ES" else en

    if decision.intent == "no_match":
        return result("no_match", decision.message.strip(), persist=False)
    if decision.intent == "save":
        return save_draft(
            repository=repository, state_store=state_store,
            session_id=session_id, user_id=user_id, language=language,
            defer_save=client_saves_routine,
        )

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
    # Any edit revokes confirmation of the previous preview, including incomplete edits.
    state.awaiting_confirmation = False
    state.saved_routine_id = None
    payload.update(state.model_dump())
    payload["intent"] = state.workflow
    if state.parameters.missing_fields:
        payload["missing_parameters"] = list(state.parameters.missing_fields)
        return result("needs_parameters", generate_response("parameters", payload))

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
            if attempt == 2:
                raise
            payload["validation_error"] = str(error)
    state.routine = generated
    state.awaiting_confirmation = True
    state.draft_id = str(uuid4())
    state.change = RoutineChange()
    return result("awaiting_confirmation", localized(
        "Here is your draft. It has not been saved. Would you like to save it, or change any exercises?",
        "Este es tu borrador. No se ha guardado. Quieres guardarlo o cambiar algun ejercicio?",
    ))


def _validate_change(previous: RoutinePlan, updated: RoutinePlan, change: RoutineChange) -> None:
    """Reject unrelated exercise edits and edits that failed to apply the request."""
    exercise_id = change.exercise_id
    if exercise_id is None:
        raise ValueError("An exercise edit requires an exercise ID.")
    if len(previous.days) != len(updated.days):
        raise ValueError("An exercise edit must preserve the other training days.")
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
