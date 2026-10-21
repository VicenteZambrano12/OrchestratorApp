"""Analyze caller-supplied history only after a validated readiness decision.

This path does not query SQL or load history from files. A first model call
decides whether the request is relevant and has records; only a ready decision
with actual supplied history permits the second analysis call.
"""

from collections.abc import Callable
from obervability.logger import Logger
from utils.past_routines_analyzer.dataclass.models import _HistoryDecision


logger = Logger.get_logger(__name__)


def handle(
    generate_response: Callable[[str, dict[str, object]], str],
    query: str,
    *,
    history: str | None = None,
    language: str = "EN",
) -> str:
    """Validate supplied text and return analysis or a readiness fallback.

    Args:
        generate_response (Callable[[str, dict[str, object]], str]): Stage adapter.
        query (str): Nonblank history question.
        history (str | None): Plain records, including serialized JSON; not a path.
        language (str): ``EN`` or ``ES``.

    Returns:
        str: Analysis, request for history, or unrelated-request message.

    Raises:
        ValueError: Input or readiness/message consistency is invalid.
        pydantic.ValidationError: The readiness answer violates its JSON schema.
        Exception: Generation failures propagate rather than inventing history.
    """
    # 1. Validate explicit history locally; never interpret it as a file location.
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
    # 2. Ask for readiness before paying for an analysis of irrelevant/missing data.
    decision = _HistoryDecision.model_validate_json(
        generate_response("parameters", payload)
    )
    if decision.status != "ready":
        if not decision.message.strip():
            raise ValueError(f"{decision.status} requires a non-empty message")
        logger.info("Supplied history analysis outcome=%s", decision.status)
        return decision.message.strip()
    # 3. Cross-check ready output against actual records before the second call.
    if history is None:
        raise ValueError("analysis requires supplied history")
    if decision.message.strip():
        raise ValueError("ready requires an empty message")
    response = generate_response("analysis", payload)
    logger.info("Supplied history analysis completed")
    return response
