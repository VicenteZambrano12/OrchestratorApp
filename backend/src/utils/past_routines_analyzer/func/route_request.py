"""Route contextual workout-history questions to validated retrieval decisions.

The model sees configured descriptions and validated prior turns in a JSON user
payload, separate from system instructions. Three identical-context attempts can
recover malformed decisions; provider failures are not swallowed or retried.
"""

import json
from collections.abc import Callable, Mapping
from typing import Any

from pydantic import ValidationError

from obervability.logger import Logger
from utils.orch.dataclass.models import MemoryTurn
from utils.past_routines_analyzer.dataclass.models import PastRoutinesRoute


logger = Logger.get_logger(__name__)


def route_request(
    generate_response: Callable[[str, str], str],
    config: Mapping[str, Any],
    query: str,
    language: str = "EN",
    memory: list[Mapping[str, object]] | None = None,
) -> PastRoutinesRoute:
    """Select an allowed history route and normalized optional day-type filter.

    Args:
        generate_response (Callable[[str, str], str]): User/system prompt adapter.
        config (Mapping[str, Any]): Validated prompts and route descriptions.
        query (str): Nonblank current history question.
        language (str): ``EN`` or ``ES``.
        memory (list[Mapping[str, object]] | None): Previous conversation turns.

    Returns:
        PastRoutinesRoute: Schema-valid decision also present in configured routes.

    Raises:
        ValueError: Query/language is invalid or three decisions are rejected.
        ValidationError: Memory fails its schema before any routing call.
        KeyError: Required configuration keys or formatting fields are missing.
        Exception: Prompt-formatting or provider failures propagate immediately.
    """
    # 1. Validate cheap request constraints before assembling provider context.
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if language not in ("EN", "ES"):
        raise ValueError("language must be ES (Spanish) or EN (English)")

    # 2. Describe configured choices and validate memory before serializing it.
    routes = config["routes"]
    data: dict[str, Any] = {
        "query": query,
        "routes": [{"id": rid, "description": desc} for rid, desc in routes.items()],
        "language": language,
    }
    if memory:
        data["memory"] = [
            MemoryTurn.model_validate(turn).model_dump(mode="json", exclude_unset=True)
            for turn in memory
        ]
    # 3. Insert JSON only in the user template; system instructions stay separate.
    prompt = config["user_prompt"].format(payload=json.dumps(data, ensure_ascii=False))

    # 4. Retry invalid output, never fall back to an arbitrary retrieval route.
    last_error: ValidationError | None = None
    for attempt in range(3):
        response = generate_response(prompt, config["system_prompt"])
        try:
            if not isinstance(response, str):
                raise ValueError("model response must be text")
            decision = PastRoutinesRoute.model_validate_json(response.strip())
        except ValidationError as error:
            last_error = error
        except ValueError:
            logger.debug("History route response was not valid text")
        else:
            if decision.route in routes:
                logger.info("History route selected route=%s", decision.route)
                return decision
        logger.warning("History route decision rejected attempt=%d max_attempts=3", attempt + 1)
    raise ValueError(
        "model failed to return a valid route decision after 3 attempts; "
        f"allowed routes: {', '.join(routes)}"
    ) from last_error
