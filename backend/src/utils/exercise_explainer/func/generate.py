"""Invoke exercise workflow stages with separate instructions and JSON context.

Name extraction requests structured JSON; per-exercise explanations request
plain text. Blank/non-text answers fail locally before downstream validation.
"""

from collections.abc import Mapping
import json

from utils.general.GeminiApiCall import GeminiClient


def generate(
    client: GeminiClient,
    prompts: Mapping[str, str],
    stage: str,
    payload: dict[str, object],
) -> str:
    """Send one stage payload to Gemini and require usable response text.

    Args:
        client (GeminiClient): Reused provider client.
        prompts (Mapping[str, str]): System instructions indexed by stage.
        stage (str): ``parameters`` for extraction, otherwise text explanation.
        payload (dict[str, object]): Query, language, optional memory/catalog row.

    Returns:
        str: Trimmed provider response.

    Raises:
        KeyError: The stage has no configured prompt.
        TypeError: Payload values are not JSON serializable.
        ValueError: The response is blank or not text.
        Exception: Provider/network failures propagate without retry here.
    """
    # 1. Keep serialized request facts separate from YAML system instructions.
    response = client.generate(
        json.dumps(payload, ensure_ascii=True),
        system_prompt=prompts[stage],
        response_mime_type="application/json" if stage == "parameters" else "text/plain",
    )
    # 2. Reject unusable text before extraction parsing or result construction.
    if not isinstance(response, str) or not response.strip():
        raise ValueError(f"Gemini returned an empty or non-text {stage} response")
    return response.strip()
