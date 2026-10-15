import json
from collections.abc import Callable, Mapping
from typing import Any

from pydantic import ValidationError

from utils.orch.dataclass.models import MemoryTurn
from utils.past_routines_analyzer.dataclass.models import PastRoutinesRoute


def route_request(
    generate_response: Callable[[str, str], str],
    config: Mapping[str, Any],
    query: str,
    language: str = "EN",
    memory: list[Mapping[str, object]] | None = None,
) -> PastRoutinesRoute:
    """Ask the model for a route and day_type, validating with up to three attempts."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if language not in ("EN", "ES"):
        raise ValueError("language must be ES (Spanish) or EN (English)")

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
    prompt = config["user_prompt"].format(payload=json.dumps(data, ensure_ascii=False))

    last_error: ValidationError | None = None
    for _ in range(3):
        response = generate_response(prompt, config["system_prompt"])
        try:
            if not isinstance(response, str):
                raise ValueError("model response must be text")
            decision = PastRoutinesRoute.model_validate_json(response.strip())
        except ValidationError as error:
            last_error = error
        except ValueError:
            continue
        else:
            if decision.route in routes:
                return decision
    raise ValueError(
        "model failed to return a valid route decision after 3 attempts; "
        f"allowed routes: {', '.join(routes)}"
    ) from last_error
