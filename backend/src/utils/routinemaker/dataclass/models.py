from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator


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


class _RoutingDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["create", "update", "no_match"]
    parameters: RoutineParameters
    message: StrictStr

    @model_validator(mode="after")
    def validate_no_match_message(self) -> "_RoutingDecision":
        if self.intent == "no_match" and not self.message.strip():
            raise ValueError("no_match requires a non-empty message")
        return self


@dataclass(frozen=True)
class RoutineMakerResult:
    """Routine-generation outcome with collected requirements and a localized message."""

    __pydantic_config__ = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "created",
                "parameters": {
                    "routine_type": "ppl",
                    "days_per_week": 3,
                    "hours_per_session": 1.0,
                    "level": "beginner",
                },
                "message": "Your three-day push/pull/legs routine is ready.",
                "routine": (
                    "Day 1 - Push: bench press, overhead press, triceps extensions.\n"
                    "Day 2 - Pull: lat pulldown, seated row, biceps curls.\n"
                    "Day 3 - Legs: squat, Romanian deadlift, calf raises."
                ),
            }
        }
    )

    status: Annotated[
        Literal["needs_parameters", "created", "updated", "no_match"],
        Field(
            description="Outcome: missing requirements, created routine, updated routine, or no match.",
            examples=["needs_parameters", "created"],
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
        str | None,
        Field(
            description="Routine text when available; null when no routine is available.",
            examples=["Day 1 - Push: bench press, overhead press, triceps extensions.", None],
        ),
    ]
