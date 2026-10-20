"""Load system prompts for the caller-supplied workout-history workflow.

Readiness and analysis are separate required stages. This loader does not load
records or SQL templates; it validates the instructions used by the stage adapter.
"""

from collections.abc import Mapping
from pathlib import Path

import yaml

from obervability.logger import Logger


logger = Logger.get_logger(__name__)


@Logger.trace(logger)
def load_prompts(prompt_path: str | Path | None = None) -> dict[str, str]:
    """Read and validate the readiness and supplied-history analysis prompts.

    Args:
        prompt_path (str | Path | None): Override or packaged analyzer YAML.

    Returns:
        dict[str, str]: Nonblank ``parameters`` and ``analysis`` system prompts.

    Raises:
        ValueError: YAML is not a mapping or a required prompt is blank/non-text.
        OSError: The file cannot be read.
        yaml.YAMLError: The file cannot be parsed.
    """
    # 1. Resolve workflow-specific instructions independently of launch location.
    path = (
        Path(prompt_path)
        if prompt_path is not None
        else Path(__file__).resolve().parents[3]
        / "config/prompts/past_routines_analyzer/past_routines_analyzer.yaml"
    )
    prompts = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(prompts, Mapping):
        raise ValueError("history prompts must be a YAML mapping")
    # 2. Reject incomplete workflows at construction, before any provider call.
    validated: dict[str, str] = {}
    for stage in ("parameters", "analysis"):
        prompt = prompts.get(stage)
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"{stage} must be a non-empty prompt")
        validated[stage] = prompt
    return validated
