import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictStr, field_validator, model_validator


class _HistoryDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["ready", "needs_history", "no_match"]
    message: StrictStr


PastRoutinesRouteId = Literal[
    "past_day_exercise", "compare_last_two_workouts", "weekly_performance"
]

# Letters, spaces, "&", "/" and "-" only, so the value is safe inside the
# SQL LIKE pattern (no % or _ wildcards) and stays a short keyword.
_DAY_TYPE_PATTERN = re.compile(r"[a-z][a-z &/-]{0,39}")


class PastRoutinesRoute(BaseModel):
    """Validated routing decision of the past routines orchestrator."""

    model_config = ConfigDict(extra="forbid", strict=True)

    route: PastRoutinesRouteId
    day_type: StrictStr | None = None

    @field_validator("day_type")
    @classmethod
    def normalize_day_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split()).lower()
        if not _DAY_TYPE_PATTERN.fullmatch(value):
            raise ValueError(
                "day_type must be a short keyword of letters, spaces, '&', '/' or '-'"
            )
        return value

    @model_validator(mode="after")
    def check_day_type_for_route(self) -> "PastRoutinesRoute":
        if self.route == "weekly_performance" and self.day_type is not None:
            raise ValueError("weekly_performance does not accept day_type; use null")
        return self


class PastRoutinesAnalysis(PastRoutinesRoute):
    """Final workflow result: the routing decision, raw rows and LLM explanation."""

    data: list[dict[str, StrictStr | int | float | None]]
    llm_explain: StrictStr

    @field_validator("llm_explain")
    @classmethod
    def check_llm_explain(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("llm_explain must not be empty")
        return value.strip()
