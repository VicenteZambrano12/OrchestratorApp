from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictStr


class _HistoryDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["ready", "needs_history", "no_match"]
    message: StrictStr


def handle(
    generate_response: Callable[[str, dict[str, object]], str],
    query: str,
    *,
    history: str | None = None,
    language: str = "EN",
) -> str:
    """Validate a history request and analyze it or ask for records."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if language not in ("EN", "ES"):
        raise ValueError("language must be EN or ES")
    if history is not None and (
        not isinstance(history, str) or not history.strip()
    ):
        raise ValueError("history must be a non-empty string when provided")
    payload: dict[str, object] = {
        "query": query,
        "language": language,
        "history": history,
    }
    decision = _HistoryDecision.model_validate_json(
        generate_response("parameters", payload)
    )
    if decision.status != "ready":
        if not decision.message.strip():
            raise ValueError(f"{decision.status} requires a non-empty message")
        return decision.message.strip()
    if history is None:
        raise ValueError("analysis requires supplied history")
    if decision.message.strip():
        raise ValueError("ready requires an empty message")
    return generate_response("analysis", payload)
