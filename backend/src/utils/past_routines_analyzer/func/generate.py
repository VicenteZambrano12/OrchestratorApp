"""Invoke the supplied-history analyzer's readiness and analysis stages.

Each call injects YAML stage instructions as a system prompt and serializes
query/language/history as user context. Readiness uses JSON; analysis uses text.
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
    """Send one supplied-history stage and require nonblank response text.

    Args:
        client (GeminiClient): Reusable configured provider client.
        prompts (Mapping[str, str]): Instructions keyed by workflow stage.
        stage (str): ``parameters`` for JSON readiness; otherwise text analysis.
        payload (dict[str, object]): Query, language, and supplied history.

    Returns:
        str: Trimmed provider response for readiness parsing or final analysis.

    Raises:
        KeyError: The requested stage has no prompt.
        TypeError: Payload values cannot be JSON serialized.
        ValueError: The provider returns blank/non-text output.
        Exception: Provider/network failures propagate without retry here.
    """
    # 1. Separate trusted stage instructions from caller-supplied history text.
    response = client.generate(
        json.dumps(payload, ensure_ascii=True),
        system_prompt=prompts[stage],
        response_mime_type="application/json" if stage == "parameters" else "text/plain",
    )
    # 2. Reject unusable answers before either JSON validation or final display.
    if not isinstance(response, str) or not response.strip():
        raise ValueError(f"Gemini returned an empty or non-text {stage} response")
    return response.strip()
