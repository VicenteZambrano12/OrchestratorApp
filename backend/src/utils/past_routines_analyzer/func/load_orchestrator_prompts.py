from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml


def load_orchestrator_prompts(prompt_path: str | Path | None = None) -> dict[str, Any]:
    """Load and validate the past routines orchestrator prompts and routes."""
    path = (
        Path(prompt_path)
        if prompt_path is not None
        else Path(__file__).resolve().parents[3]
        / "config/prompts/past_routines_analyzer/orchestrator.yaml"
    )
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, Mapping):
        raise ValueError("orchestrator prompts must be a YAML mapping")
    for name in ("system_prompt", "user_prompt"):
        prompt = config.get(name)
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"{name} must be a non-empty string")
    if "{payload}" not in config["user_prompt"]:
        raise ValueError("user_prompt must contain {payload}")
    routes = config.get("routes")
    if not isinstance(routes, Mapping) or not routes:
        raise ValueError("routes must be a non-empty mapping")
    for route_id, description in routes.items():
        if not isinstance(route_id, str) or not route_id.strip():
            raise ValueError("each route must have a non-empty string id")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"route {route_id} must have a non-empty description")
    return {
        "system_prompt": config["system_prompt"],
        "user_prompt": config["user_prompt"],
        "routes": dict(routes),
    }
