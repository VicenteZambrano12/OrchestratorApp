from collections.abc import Mapping
import json

from utils.general.GeminiApiCall import GeminiClient
from utils.past_routines_analyzer.dataclass.models import PastRoutinesRoute


def explain_history(
    client: GeminiClient,
    system_prompt: str,
    query: str,
    language: str,
    decision: PastRoutinesRoute,
    data: list[dict[str, object]],
    memory: list[Mapping[str, object]] | None = None,
) -> str:
    """Ask Gemini to explain the retrieved rows and return non-empty text."""
    payload: dict[str, object] = {
        "query": query,
        "language": language,
        "route": decision.route,
        "day_type": decision.day_type,
        "data": data,
    }
    if memory:
        payload["memory"] = list(memory)
    response = client.generate(
        json.dumps(payload, ensure_ascii=False, default=str),
        system_prompt=system_prompt,
        response_mime_type="text/plain",
    )
    if not isinstance(response, str) or not response.strip():
        raise ValueError("Gemini returned an empty or non-text explanation")
    return response.strip()
