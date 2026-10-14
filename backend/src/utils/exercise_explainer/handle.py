from collections.abc import Callable
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StrictStr, StringConstraints


class _ExerciseDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    exercises: list[
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    ]
    message: StrictStr


def handle(
    generate_response: Callable[[str, dict[str, object]], str],
    query: str,
    *,
    language: str = "EN",
) -> str:
    """Validate a request, collect names, or explain the supplied exercises."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if language not in ("EN", "ES"):
        raise ValueError("language must be EN or ES")
    payload: dict[str, object] = {"query": query, "language": language}
    decision = _ExerciseDecision.model_validate_json(
        generate_response("parameters", payload)
    )
    if not decision.exercises:
        if not decision.message.strip():
            raise ValueError("missing exercises requires a non-empty message")
        return decision.message.strip()
    if decision.message.strip():
        raise ValueError("named exercises requires an empty message")
    payload["parameters"] = {"exercises": decision.exercises}
    return generate_response("explanation", payload)
