from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RoutineParameters(BaseModel):
    """Known requirements; None means the user still needs to supply a value."""

    model_config = ConfigDict(extra="forbid")

    routine_type: Literal["weider", "ppl"] | None = None
    days_per_week: int | None = Field(default=None, strict=True, ge=1, le=7)
    hours_per_session: float | None = Field(
        default=None, strict=True, gt=0, le=24, allow_inf_nan=False
    )
    level: Literal["beginner", "intermediate", "advanced"] | None = None

    @property
    def missing_fields(self) -> tuple[str, ...]:
        return tuple(
            name for name, value in self.model_dump().items() if value is None
        )


@dataclass(frozen=True)
class RoutineMakerResult:
    status: Literal["needs_parameters", "created", "updated", "no_match"]
    parameters: RoutineParameters
    message: str
    routine: str | None
