from collections.abc import Mapping
from pathlib import Path

import yaml


def load_prompts(prompt_path: str | Path | None = None) -> dict[str, str]:
    """Load and validate the workout history workflow prompts."""
    path = (
        Path(prompt_path)
        if prompt_path is not None
        else Path(__file__).resolve().parents[2]
        / "config/prompts/past_routines_analyzer/past_routines_analyzer.yaml"
    )
    prompts = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(prompts, Mapping):
        raise ValueError("history prompts must be a YAML mapping")
    validated: dict[str, str] = {}
    for stage in ("parameters", "analysis"):
        prompt = prompts.get(stage)
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"{stage} must be a non-empty prompt")
        validated[stage] = prompt
    return validated
