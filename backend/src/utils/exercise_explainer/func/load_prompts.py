from collections.abc import Mapping
from pathlib import Path

import yaml


def load_prompts(prompt_path: str | Path | None = None) -> dict[str, str]:
    """Load and validate the exercise workflow prompts."""
    path = (
        Path(prompt_path)
        if prompt_path is not None
        else Path(__file__).resolve().parents[3]
        / "config/prompts/exercise_explainer/exercise_explainer.yaml"
    )
    prompts = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(prompts, Mapping):
        raise ValueError("exercise prompts must be a YAML mapping")
    validated: dict[str, str] = {}
    for stage in ("parameters", "explanation"):
        prompt = prompts.get(stage)
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"{stage} must be a non-empty prompt")
        validated[stage] = prompt
    return validated
