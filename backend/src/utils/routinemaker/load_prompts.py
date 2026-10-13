from collections.abc import Mapping
from pathlib import Path

import yaml


def load_prompts(prompt_path: str | Path | None = None) -> dict[str, str]:
    """Load and validate the four routine workflow prompts."""
    path = (
        Path(prompt_path)
        if prompt_path is not None
        else Path(__file__).resolve().parents[2]
        / "config/prompts/routinemaker/routinemaker.yaml"
    )
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
