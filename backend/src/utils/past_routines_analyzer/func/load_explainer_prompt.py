"""Load instructions for explaining SQL-backed workout-history results.

Only a nonblank explanation string is accepted; it later becomes Gemini's
system instruction while rows and conversation context remain user payload.
"""

from collections.abc import Mapping
from pathlib import Path

import yaml

from obervability.logger import Logger


logger = Logger.get_logger(__name__)


@Logger.trace(logger)
def load_explainer_prompt(prompt_path: str | Path | None = None) -> str:
    """Read the explanation system prompt from YAML.

    Args:
        prompt_path (str | Path | None): Override or packaged explainer YAML.

    Returns:
        str: Unmodified nonblank ``explanation`` instruction.

    Raises:
        ValueError: YAML is not a mapping or explanation is missing/blank/non-text.
        OSError: The file cannot be read.
        yaml.YAMLError: The file cannot be parsed.
    """
    # 1. Resolve a source-relative default rather than depending on launch location.
    path = (
        Path(prompt_path)
        if prompt_path is not None
        else Path(__file__).resolve().parents[3]
        / "config/prompts/past_routines_analyzer/explainer.yaml"
    )
    # 2. Fail before workflow execution if the model would lack its instructions.
    prompts = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(prompts, Mapping):
        raise ValueError("explainer prompts must be a YAML mapping")
    prompt = prompts.get("explanation")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("explanation must be a non-empty prompt")
    return prompt
