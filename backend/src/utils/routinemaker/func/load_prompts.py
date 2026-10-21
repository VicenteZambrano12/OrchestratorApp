"""Load the system instructions used by routine-maker workflow stages.

Prompt files are resolved relative to the source tree unless explicitly
overridden. All required stages are validated together so a workflow cannot
start with a missing routing, requirement, creation, or update instruction.
"""

from collections.abc import Mapping
from pathlib import Path

import yaml

from obervability.logger import Logger


logger = Logger.get_logger(__name__)


@Logger.trace(logger)
def load_prompts(prompt_path: str | Path | None = None) -> dict[str, str]:
    """Read and validate the four routine workflow system prompts.

    Args:
        prompt_path: Optional YAML path; None uses the bundled routine prompts.

    Returns:
        dict[str, str]: Nonblank ``routing``, ``parameters``, ``routine_maker``,
            and ``routine_updater`` prompts, preserving their original text.

    Raises:
        OSError: The prompt file cannot be read.
        yaml.YAMLError: Prompt YAML cannot be parsed.
        ValueError: The document is not a mapping or a required prompt is blank
            or not a string.
    """
    # 1. Resolve prompts independently of the server's working directory.
    path = (
        Path(prompt_path)
        if prompt_path is not None
        else Path(__file__).resolve().parents[3]
        / "config/prompts/routinemaker/routinemaker.yaml"
    )
    # 2. Reject incomplete prompt configuration before any provider invocation.
    prompts = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(prompts, Mapping):
        raise ValueError("routine prompts must be a YAML mapping")
    validated: dict[str, str] = {}
    for name in ("routing", "parameters", "routine_maker", "routine_updater"):
        prompt = prompts.get(name)
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"{name} must be a non-empty prompt")
        validated[name] = prompt
    return validated
