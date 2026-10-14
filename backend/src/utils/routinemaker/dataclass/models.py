from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator


ROUTINE_PLAN_EXAMPLE = {
    "name": "Push day",
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
    """Known requirements; None means the user still needs to supply a value."""

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
        return tuple(
            name for name, value in self.model_dump().items() if value is None
        )


class RoutineChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["add", "remove", "replace", "adjust"] | None = None
    day: int | None = Field(default=None, strict=True, ge=1, le=7)
    exercise_id: int | None = Field(default=None, strict=True, gt=0)
    replacement_exercise_id: int | None = Field(default=None, strict=True, gt=0)
    details: str | None = Field(default=None, min_length=1)

    @property
    def missing_fields(self) -> list[str]:
        missing = [name for name in ("action", "day", "exercise_id") if getattr(self, name) is None]
        if self.action == "replace" and self.replacement_exercise_id is None:
            missing.append("replacement_exercise_id")
        if self.action == "adjust" and not self.details:
            missing.append("details")
        return missing


class RoutineExercise(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exercise_id: int = Field(strict=True, gt=0)
    name: str = ""
    sets: int = Field(strict=True, ge=1, le=20)
    reps: str = Field(min_length=1)
    rest_seconds: int = Field(strict=True, ge=0, le=900)
    notes: str = ""


class RoutineDay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: int = Field(strict=True, ge=1, le=7)
    day_type: str = Field(min_length=1)
    info: str = Field(min_length=1)
    duration_minutes: float = Field(gt=0, allow_inf_nan=False)
    exercises: list[RoutineExercise] = Field(min_length=1)


class RoutinePlan(BaseModel):
    """A weekly routine containing only catalog exercise references."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    days: list[RoutineDay] = Field(min_length=1, max_length=7)
    recovery: str = Field(min_length=1)


class _RoutingDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["create", "update_saved", "update_draft", "save", "no_match"]
    parameters: RoutineParameters
    message: StrictStr
    routine_id: int | None = Field(default=None, strict=True, gt=0)
    change: RoutineChange = Field(default_factory=RoutineChange)
    start_new: bool = False

    @model_validator(mode="after")
    def validate_no_match_message(self) -> "_RoutingDecision":
        if self.intent == "no_match" and not self.message.strip():
            raise ValueError("no_match requires a non-empty message")
        if self.intent == "save" and (
            self.parameters.model_fields_set or self.change.model_fields_set
            or self.start_new or self.routine_id is not None
        ):
            raise ValueError("save must only confirm the preview, without parameters or edits")
        return self


class RoutineState(BaseModel):
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
    """Routine-generation outcome with collected requirements and a localized message."""

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
        Literal["needs_parameters", "needs_changes", "needs_routine", "awaiting_confirmation", "saved", "no_match"],
        Field(
            description="Draft workflow outcome. Only saved indicates a database write.",
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
