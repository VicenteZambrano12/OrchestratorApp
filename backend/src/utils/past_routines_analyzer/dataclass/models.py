"""Strict decisions and results for supplied-history and SQL-backed analysis.

Routing constrains both the SQL template choice and optional day-type filter.
Public results retain raw database rows separately from generated explanations;
validators normalize filters and reject invalid route/filter combinations.
"""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictStr, field_validator, model_validator


class _HistoryDecision(BaseModel):
    """Parse the supplied-history workflow's readiness decision.

    Attributes:
        status (Literal["ready", "needs_history", "no_match"]): Whether to analyze,
            request records, or decline an unrelated request.
        message (StrictStr): User-facing fallback; the handler requires empty
            text for ready decisions and nonblank text otherwise.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["ready", "needs_history", "no_match"]
    message: StrictStr


PastRoutinesRouteId = Literal[
    "past_day_exercise", "compare_last_two_workouts", "weekly_performance"
]

# 1. Bound filter length and exclude LIKE wildcards before SQL parameter binding.
_DAY_TYPE_PATTERN = re.compile(r"[a-z][a-z &/-]{0,39}")


class PastRoutinesRoute(BaseModel):
    """Constrain SQL retrieval to a supported route and normalized day keyword.

    Attributes:
        route (PastRoutinesRouteId): ``past_day_exercise``,
            ``compare_last_two_workouts``, or ``weekly_performance``.
        day_type (StrictStr | None): Lowercase, space-normalized keyword of at
            most 40 characters; None means no day filter and is required weekly.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    route: PastRoutinesRouteId
    day_type: StrictStr | None = None

    @field_validator("day_type")
    @classmethod
    def normalize_day_type(cls, value: str | None) -> str | None:
        """Normalize a filter while preventing wildcard or oversized keywords.

        Args:
            value (str | None): Parsed strict-string filter or no filter.

        Returns:
            str | None: Lowercase collapsed-whitespace keyword, or None.

        Raises:
            ValueError: The normalized value violates the restricted pattern.
        """
        # 1. Preserve the no-filter sentinel; validate only normalized keywords.
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
        """Enforce the weekly SQL route's unfiltered-day contract.

        Returns:
            PastRoutinesRoute: This validated decision.

        Raises:
            ValueError: Weekly performance is paired with a day filter.
        """
        # 1. Prevent a filter the weekly template does not accept.
        if self.route == "weekly_performance" and self.day_type is not None:
            raise ValueError("weekly_performance does not accept day_type; use null")
        return self


class PastRoutinesAnalysis(PastRoutinesRoute):
    """Return the validated routing decision, exact rows, and generated prose.

    Attributes:
        route (PastRoutinesRouteId): Inherited supported retrieval route.
        day_type (StrictStr | None): Inherited normalized optional day filter.
        data (list[dict[str, StrictStr | int | float | None]]): Database rows;
            not reconstructed from model output.
        llm_explain (StrictStr): Trimmed nonblank explanation of those rows.
    """

    data: list[dict[str, StrictStr | int | float | None]]
    llm_explain: StrictStr

    @field_validator("llm_explain")
    @classmethod
    def check_llm_explain(cls, value: str) -> str:
        """Require a meaningful explanation before exposing a workflow result.

        Args:
            value (str): Parsed strict-string provider explanation.

        Returns:
            str: Trimmed explanation.

        Raises:
            ValueError: The explanation contains only whitespace.
        """
        # 1. Do not report a successful analysis with an empty narrative.
        if not value.strip():
            raise ValueError("llm_explain must not be empty")
        return value.strip()
