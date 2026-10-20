"""Load stage-specific exercise system instructions from packaged or custom YAML.

Both extraction and explanation prompts must exist before a workflow is usable;
the returned strings are injected as system prompts, not user-context fields.
"""

from collections.abc import Mapping
from pathlib import Path

import yaml

from obervability.logger import Logger


logger = Logger.get_logger(__name__)


@Logger.trace(logger)
def load_prompts(prompt_path: str | Path | None = None) -> dict[str, str]:
    """Read required exercise prompts and discard unrelated YAML keys.

    Args:
        prompt_path (str | Path | None): Override file, or packaged exercise YAML.

    Returns:
        dict[str, str]: Nonblank ``parameters`` and ``explanation`` instructions.

    Raises:
        ValueError: YAML is not a mapping or a required prompt is blank/non-text.
        OSError: The prompt file cannot be read.
        yaml.YAMLError: The prompt file cannot be parsed.
    """
    # 1. Resolve instructions independently of the process working directory.
    path = (
        Path(prompt_path)
        if prompt_path is not None
        else Path(__file__).resolve().parents[3]
        / "config/prompts/exercise_explainer/exercise_explainer.yaml"
    )
    prompts = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(prompts, Mapping):
        raise ValueError("exercise prompts must be a YAML mapping")
    # 2. Fail initialization rather than invoke a stage with missing instructions.
    validated: dict[str, str] = {}
    for stage in ("parameters", "explanation"):
        prompt = prompts.get(stage)
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"{stage} must be a non-empty prompt")
        validated[stage] = prompt
    return validated
