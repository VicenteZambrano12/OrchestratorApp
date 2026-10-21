"""Generate prose from SQL rows without replacing the authoritative data result.

The selected route, filter, query, language, rows, and optional prior turns are
serialized as user context. The loaded explanation instruction is supplied
through Gemini's system-prompt channel.
"""

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
    """Invoke one text-generation call grounded in retrieved workout records.

    Args:
        client (GeminiClient): Reused provider client.
        system_prompt (str): Validated explanation instructions.
        query (str): Current history question.
        language (str): Requested response language.
        decision (PastRoutinesRoute): Validated route and optional day filter.
        data (list[dict[str, object]]): Exact retrieved rows, including an empty list.
        memory (list[Mapping[str, object]] | None): Prior turns for follow-ups.

    Returns:
        str: Trimmed nonblank explanation.

    Raises:
        ValueError: The provider returns blank/non-text output.
        Exception: Provider/network failures propagate without fabricated analysis.
    """
    # 1. Ground the narrative in the actual route and rows, not a model-made dataset.
    payload: dict[str, object] = {
        "query": query,
        "language": language,
        "route": decision.route,
        "day_type": decision.day_type,
        "data": data,
    }
    if memory:
        payload["memory"] = list(memory)
    # 2. Stringify provider-specific scalar values without changing returned rows.
    response = client.generate(
        json.dumps(payload, ensure_ascii=False, default=str),
        system_prompt=system_prompt,
        response_mime_type="text/plain",
    )
    # 3. Treat empty output as a failure rather than a successful empty analysis.
    if not isinstance(response, str) or not response.strip():
        raise ValueError("Gemini returned an empty or non-text explanation")
    return response.strip()
