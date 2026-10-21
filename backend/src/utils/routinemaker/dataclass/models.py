"""Define typed contracts and guardrails for routine generation and persistence.

Pydantic models separate collected user requirements, requested edits, generated
plans, routing decisions, and session-cached workflow state. Context-aware plan
validation checks generated output against the exercise catalog and available
training time before confirmation. Legacy models expose saved workout templates
without inventing missing duration or rest guidance. The immutable result
envelope carries workflow outcomes back to the pipeline and HTTP response layer.
"""

from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationInfo, model_validator


ROUTINE_PLAN_EXAMPLE = {
    "name": "Push day",
    "summary": "A focused push session to build upper-body strength with controlled repetitions.",
    "days": [{
        "day": 1, "day_type": "push", "info": "Warm up before training.",
        "duration_minutes": 45.0,
        "exercises": [{
            "exercise_id": 1, "name": "Barbell Bench Press", "sets": 3,
            "reps": "8-12", "rest_seconds": 90, "notes": "Use controlled technique.",
        }],
    }],
    "recovery": "Rest between sessions.",
}


class RoutineParameters(BaseModel):
    """Collect routine requirements while preserving unknown values as None.

    Attributes:
        routine_type (Literal["weider", "ppl"] | None): Requested split.
        days_per_week (int | None): Strict integer from one through seven.
        hours_per_session (float | None): Finite positive hours, at most 24.
        level (Literal["beginner", "intermediate", "advanced"] | None):
            Experience level used to filter the exercise catalog.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "routine_type": "ppl",
                "days_per_week": 3,
                "hours_per_session": 1.0,
                "level": "beginner",
            }
        },
    )

    routine_type: Literal["weider", "ppl"] | None = Field(
        default=None,
        description="Workout split: weider or push/pull/legs (ppl); null if not yet supplied.",
        examples=["ppl", None],
    )
    days_per_week: int | None = Field(
        default=None, strict=True, ge=1, le=7,
        description="Training days per week, from 1 to 7; null if not yet supplied.",
        examples=[3, None],
    )
    hours_per_session: float | None = Field(
        default=None, strict=True, gt=0, le=24, allow_inf_nan=False,
        description="Available hours per session, greater than 0 and at most 24; null if unknown.",
        examples=[1.0, None],
    )
    level: Literal["beginner", "intermediate", "advanced"] | None = Field(
        default=None,
        description="Training experience level; null if the user has not supplied it.",
        examples=["beginner", None],
    )

    @property
    def missing_fields(self) -> tuple[str, ...]:
        """Identify requirements still needed before generating a plan.

        Returns:
            tuple[str, ...]: Field names whose current values are None, in
                model field order.
        """
        # 1. Preserve unknown requirements instead of letting the model infer them.
        return tuple(
            name for name, value in self.model_dump().items() if value is None
        )


class RoutineChange(BaseModel):
    """Describe an exercise edit independently of the generated plan.

    Attributes:
        action (Literal["add", "remove", "replace", "adjust"] | None):
            Requested operation, or None when not collected.
        day (int | None): One-based training day from one through seven.
        exercise_id (int | None): Positive catalog ID targeted by the edit.
        replacement_exercise_id (int | None): Positive replacement ID.
        details (str | None): Nonempty adjustment instructions when supplied.
    """

    model_config = ConfigDict(extra="forbid")

    action: Literal["add", "remove", "replace", "adjust"] | None = None
    day: int | None = Field(default=None, strict=True, ge=1, le=7)
    exercise_id: int | None = Field(default=None, strict=True, gt=0)
    replacement_exercise_id: int | None = Field(default=None, strict=True, gt=0)
    details: str | None = Field(default=None, min_length=1)

    @property
    def missing_fields(self) -> list[str]:
        """Identify fields required to execute the requested edit.

        Returns:
            list[str]: Missing common fields plus replacement or adjustment
                details required by the selected action.
        """
        # 1. Require explicit edit targets rather than permitting speculative changes.
        missing = [name for name in ("action", "day", "exercise_id") if getattr(self, name) is None]
        if self.action == "replace" and self.replacement_exercise_id is None:
            missing.append("replacement_exercise_id")
        if self.action == "adjust" and not self.details:
            missing.append("details")
        return missing


class RoutineExercise(BaseModel):
    """Represent one catalog-referenced exercise prescription.

    Attributes:
        exercise_id (int): Positive strict catalog identifier.
        name (str): Display name, replaced from catalog during contextual validation.
        sets (int): Strict set count from one through twenty.
        reps (str): Nonempty repetition prescription.
        rest_seconds (int): Strict rest interval from zero through 900 seconds.
        notes (str): Optional textual training guidance, defaulting to empty.
    """

    model_config = ConfigDict(extra="forbid")

    exercise_id: int = Field(strict=True, gt=0)
    name: str = ""
    sets: int = Field(strict=True, ge=1, le=20)
    reps: str = Field(min_length=1)
    rest_seconds: int = Field(strict=True, ge=0, le=900)
    notes: str = ""


class RoutineDay(BaseModel):
    """Group exercise prescriptions into a timed training day.

    Attributes:
        day (int): Strict day number from one through seven.
        day_type (str): Nonempty training-day label.
        info (str): Nonempty day-level instructions.
        duration_minutes (float): Finite positive session duration.
        exercises (list[RoutineExercise]): Nonempty exercise sequence.
    """

    model_config = ConfigDict(extra="forbid")

    day: int = Field(strict=True, ge=1, le=7)
    day_type: str = Field(min_length=1)
    info: str = Field(min_length=1)
    duration_minutes: float = Field(gt=0, allow_inf_nan=False)
    exercises: list[RoutineExercise] = Field(min_length=1)


class LegacyRoutineExercise(RoutineExercise):
    """Expose a saved template exercise without fabricated rest guidance.

    Attributes:
        rest_seconds (None): Rest timing was not recorded in legacy storage.
        exercise_id (int): Positive catalog identifier inherited from the base.
        name (str): Stored exercise display name.
        sets (int): Set count, retaining the base model's one-to-twenty constraint.
        reps (str): Nonempty stored repetition description.
        notes (str): Stored set metrics or descriptive guidance.
    """

    rest_seconds: None = None


class LegacyRoutineDay(RoutineDay):
    """Represent one legacy workout template as a displayable routine day.

    Attributes:
        day (int): Positive display position without the modern seven-day limit.
        routine_id (int): Positive source template identifier.
        duration_minutes (None): Session duration was not recorded.
        exercises (list[LegacyRoutineExercise]): Nonempty legacy exercise list.
        day_type (str): Inherited nonempty training-day label.
        info (str): Inherited nonempty day-level description.
    """

    day: int = Field(strict=True, ge=1)
    routine_id: int = Field(strict=True, gt=0)
    duration_minutes: None = None
    exercises: list[LegacyRoutineExercise] = Field(min_length=1)


class LegacyRoutinePlan(BaseModel):
    """Expose legacy templates without claiming modern generation completeness.

    Attributes:
        storage_format (Literal["legacy"]): Legacy-format discriminator.
        name (str): Combined template display name.
        summary (str): Description of the reconstructed templates.
        recovery (str): Recovery description or explicit unavailable-data text.
        days (list[LegacyRoutineDay]): Nonempty reconstructed template sequence.
    """

    model_config = ConfigDict(extra="forbid")

    storage_format: Literal["legacy"] = "legacy"
    name: str
    summary: str
    recovery: str
    days: list[LegacyRoutineDay] = Field(min_length=1)


class RoutinePlan(BaseModel):
    """Hold a weekly plan with optional context-aware generation validation.

    Attributes:
        name (str): Nonempty routine title.
        summary (str): Plan explanation, at most 600 characters; defaults to empty.
        days (list[RoutineDay]): One through seven training days.
        recovery (str): Nonempty recovery guidance.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    summary: str = Field(default="", max_length=600)
    days: list[RoutineDay] = Field(min_length=1, max_length=7)
    recovery: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_catalog_plan(self, info: ValidationInfo) -> "RoutinePlan":
        """Check generated plans against supplied requirements and catalog.

        Args:
            info: Pydantic validation context. When present, it must contain
                ``parameters`` and ``catalog``; ``require_summary`` optionally
                requires a nonblank summary.

        Returns:
            RoutinePlan: This plan, with exercise names replaced by catalog names.
                Without context, only normal field validation applies.

        Raises:
            ValueError: Summary, day count/order, timing, exercise uniqueness,
                catalog membership, or catalog names violate the guardrails.
            KeyError: A supplied validation context lacks required entries.
        """
        # 1. Permit ordinary deserialization without generation-specific context.
        if not info.context:
            return self
        # 2. Enforce user requirements before accepting a generated preview.
        if info.context.get("require_summary") and not self.summary.strip():
            raise ValueError("Routine requires a brief summary explaining the plan.")
        parameters = info.context["parameters"]
        catalog = {row["id"]: row for row in info.context["catalog"]}
        if len(self.days) != parameters.days_per_week:
            raise ValueError("Routine must contain exactly days_per_week training days.")
        if [day.day for day in self.days] != list(range(1, len(self.days) + 1)):
            raise ValueError("Routine day numbers must be consecutive and unique, starting at 1.")
        # 3. Reject unsupported prescriptions and replace model-authored catalog names.
        for day in self.days:
            if parameters.hours_per_session is None or day.duration_minutes > parameters.hours_per_session * 60:
                raise ValueError("Routine session duration exceeds the requested time.")
            ids = [exercise.exercise_id for exercise in day.exercises]
            if len(ids) != len(set(ids)):
                raise ValueError("An exercise may occur only once per training day.")
            if not set(ids).issubset(catalog):
                raise ValueError("Routine contains unknown exercise IDs or exercises above the requested level.")
            for exercise in day.exercises:
                name = catalog[exercise.exercise_id]["name"]
                if not isinstance(name, str):
                    raise ValueError("Catalog exercise names must be strings.")
                exercise.name = name
        return self


class _RoutingDecision(BaseModel):
    """Validate the routine agent's structured action-classification output.

    Attributes:
        intent (Literal["create", "update_saved", "update_draft", "save", "no_match"]):
            Selected workflow branch.
        parameters (RoutineParameters): Requirements extracted from the query.
        message (str): Strict text, nonblank for unsupported requests.
        routine_id (int | None): Positive saved routine selected for editing.
        change (RoutineChange): Collected exercise edit, empty by default.
        start_new (bool): Whether creation should discard the previous draft.
    """

    model_config = ConfigDict(extra="forbid")

    intent: Literal["create", "update_saved", "update_draft", "save", "no_match"]
    parameters: RoutineParameters
    message: StrictStr
    routine_id: int | None = Field(default=None, strict=True, gt=0)
    change: RoutineChange = Field(default_factory=RoutineChange)
    start_new: bool = False

    @model_validator(mode="after")
    def validate_no_match_message(self) -> "_RoutingDecision":
        """Require useful no-match text and confirmation-only save decisions.

        Returns:
            _RoutingDecision: This validated classification.

        Raises:
            ValueError: A no-match reply is blank, or save also proposes new
                requirements, edits, a reset, or a routine selection.
        """
        # 1. Keep unsupported requests explicit and save confirmations unambiguous.
        if self.intent == "no_match" and not self.message.strip():
            raise ValueError("no_match requires a non-empty message")
        if self.intent == "save" and (
            self.parameters.model_fields_set or self.change.model_fields_set
            or self.start_new or self.routine_id is not None
        ):
            raise ValueError("save must only confirm the preview, without parameters or edits")
        return self


class RoutineState(BaseModel):
    """Cache one user's routine workflow within a caller-supplied session.

    Attributes:
        parameters (RoutineParameters): Collected generation requirements.
        routine (RoutinePlan | None): Current preview or selected saved plan.
        source_routine_id (int | None): Saved version from which an edit began.
        workflow (Literal["create", "update_saved", "update_draft"]): Active branch.
        change (RoutineChange): Pending exercise edit.
        awaiting_confirmation (bool): Whether the current preview may be confirmed.
        draft_id (str | None): Identity of the latest generated preview.
        saved_routine_id (int | None): Persisted version for an already saved draft.
        requests (list[str]): Queries accumulated within the workflow.
        selection_parameters (dict[str, object]): Requirements collected while
            waiting for the user to choose a saved routine.
    """

    model_config = ConfigDict(extra="forbid")

    parameters: RoutineParameters = Field(default_factory=RoutineParameters)
    routine: RoutinePlan | None = None
    source_routine_id: int | None = None
    workflow: Literal["create", "update_saved", "update_draft"] = "create"
    change: RoutineChange = Field(default_factory=RoutineChange)
    awaiting_confirmation: bool = False
    draft_id: str | None = None
    saved_routine_id: int | None = None
    requests: list[str] = Field(default_factory=list)
    selection_parameters: dict[str, object] = Field(default_factory=dict)


@dataclass(frozen=True)
class RoutineMakerResult:
    """Return an immutable routine workflow outcome to the pipeline and API.

    Attributes:
        status (Literal["needs_parameters", "needs_changes", "needs_routine",
            "awaiting_confirmation", "save_requested", "saved", "no_match"]):
            Workflow outcome; only ``saved`` denotes completed persistence.
        parameters (RoutineParameters): Requirements collected so far.
        message (str): Localized explanation or follow-up request.
        routine (RoutinePlan | None): Structured plan when available.
        routine_id (int | None): Persisted version ID, otherwise None.
        draft_id (str | None): Preview identity for direct client confirmation.
    """

    __pydantic_config__ = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "awaiting_confirmation",
                "parameters": {
                    "routine_type": "ppl",
                    "days_per_week": 1,
                    "hours_per_session": 1.0,
                    "level": "beginner",
                },
                "message": "Your draft is ready. Would you like to save it?",
                "routine": ROUTINE_PLAN_EXAMPLE,
            }
        }
    )

    status: Annotated[
        Literal["needs_parameters", "needs_changes", "needs_routine", "awaiting_confirmation", "save_requested", "saved", "no_match"],
        Field(
            description="Draft workflow outcome. save_requested asks the client to persist the confirmed draft; only saved indicates a database write.",
            examples=["needs_parameters", "awaiting_confirmation", "saved"],
        ),
    ]
    parameters: Annotated[
        RoutineParameters,
        Field(
            description="Collected workout requirements; unknown values remain null.",
            examples=[{
                "routine_type": "ppl",
                "days_per_week": 3,
                "hours_per_session": 1.0,
                "level": "beginner",
            }],
        ),
    ]
    message: Annotated[
        str,
        Field(
            description="Localized explanation, follow-up question, or outcome message.",
            examples=["What is your training level?"],
        ),
    ]
    routine: Annotated[
        RoutinePlan | None,
        Field(
            description="Structured weekly routine with catalog exercise IDs, or null.",
            examples=[None],
        ),
    ]
    routine_id: Annotated[
        int | None,
        Field(description="ID of the newly saved version, otherwise null.", examples=[None, 1]),
    ] = None
    draft_id: Annotated[
        str | None,
        Field(
            description="Preview identifier required by the direct-save endpoint; null without a saveable draft.",
            examples=[None, "draft-123"],
        ),
    ] = None
