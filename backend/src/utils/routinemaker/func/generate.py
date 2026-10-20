"""Translate routine workflow stages into Gemini generation requests.

Stage-specific system prompts constrain routing, requirement collection, plan
creation, and plan updates. Structured stages request JSON, while requirement
questions request text; the workflow applies the corresponding Pydantic schemas
after this transport adapter returns.
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
    """Invoke Gemini with a stage prompt and serialized workflow context.

    Args:
        client: Configured synchronous Gemini transport.
        prompts: Stage names mapped to validated system instructions.
        stage: Prompt key; ``parameters`` requests text and other stages JSON.
        payload: JSON-serializable query, state, catalog, and validation context.

    Returns:
        str: Stripped model output, pending workflow-level schema validation.

    Raises:
        KeyError: The requested stage has no configured prompt.
        TypeError: The payload is not JSON serializable.
        ValueError: Output is not text, a parameters reply is blank, or the
            client rejects generation input.
        RuntimeError: The client receives no usable generation.
        urllib.error.URLError: A provider HTTP or network request fails.
        TimeoutError: The provider request times out.
    """
    # 1. Separate stage instructions from serialized user and workflow context.
    response = client.generate(
        json.dumps(payload, ensure_ascii=True),
        system_prompt=prompts[stage],
        response_mime_type="text/plain" if stage == "parameters" else "application/json",
    )
    # 2. Guard the text contract before downstream schema validation and retries.
    if not isinstance(response, str) or (stage == "parameters" and not response.strip()):
        raise ValueError(f"Gemini returned an empty or non-text {stage} response")
    return response.strip()
