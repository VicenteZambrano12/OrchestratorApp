from collections.abc import Mapping
from pathlib import Path

import yaml


def load_explainer_prompt(prompt_path: str | Path | None = None) -> str:
    """Load and validate the system prompt that explains retrieved history."""
    path = (
        Path(prompt_path)
        if prompt_path is not None
        else Path(__file__).resolve().parents[3]
        / "config/prompts/past_routines_analyzer/explainer.yaml"
    )
    prompts = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(prompts, Mapping):
        raise ValueError("explainer prompts must be a YAML mapping")
    prompt = prompts.get("explanation")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("explanation must be a non-empty prompt")
    return prompt
