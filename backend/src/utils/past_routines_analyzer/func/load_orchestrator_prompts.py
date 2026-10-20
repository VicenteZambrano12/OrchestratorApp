"""Load the second-level history router's instructions and target descriptions.

The returned route mapping supplies both model-visible choices and the runtime
allowlist. The user template must contain a payload slot; formatting and the
fixed Pydantic route vocabulary are checked later by the routing helper.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from obervability.logger import Logger


logger = Logger.get_logger(__name__)


@Logger.trace(logger)
def load_orchestrator_prompts(prompt_path: str | Path | None = None) -> dict[str, Any]:
    """Read required routing prompts and nonempty route descriptions.

    Args:
        prompt_path (str | Path | None): Override or packaged history-router YAML.

    Returns:
        dict[str, Any]: System instruction, user template, and copied routes map.

    Raises:
        ValueError: YAML shape, prompt text, payload slot, or routes are invalid.
        OSError: The prompt file cannot be read.
        yaml.YAMLError: The prompt file cannot be parsed.
    """
    # 1. Resolve configuration once for reuse across routing invocations.
    path = (
        Path(prompt_path)
        if prompt_path is not None
        else Path(__file__).resolve().parents[3]
        / "config/prompts/past_routines_analyzer/orchestrator.yaml"
    )
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, Mapping):
        raise ValueError("orchestrator prompts must be a YAML mapping")
    # 2. Require instruction and context channels without pre-formatting user data.
    for name in ("system_prompt", "user_prompt"):
        prompt = config.get(name)
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"{name} must be a non-empty string")
    if "{payload}" not in config["user_prompt"]:
        raise ValueError("user_prompt must contain {payload}")
    # 3. Ensure each model-visible choice has usable identity and meaning.
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
