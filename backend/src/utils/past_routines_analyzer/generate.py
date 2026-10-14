from collections.abc import Mapping
import json

from utils.general.GeminiApiCall import GeminiClient


def generate(
    client: GeminiClient,
    prompts: Mapping[str, str],
    stage: str,
    payload: dict[str, object],
) -> str:
    """Call Gemini with a stage prompt and validate the returned text."""
    response = client.generate(
        json.dumps(payload, ensure_ascii=True),
        system_prompt=prompts[stage],
    )
    if not isinstance(response, str) or not response.strip():
        raise ValueError(f"Gemini returned an empty or non-text {stage} response")
    return response.strip()
