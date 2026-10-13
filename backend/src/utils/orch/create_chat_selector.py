import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import yaml


def create_chat_selector(
	chat_model: Callable[[list[dict[str, str]]], str],
	prompt_path: str | Path | None = None,
) -> Callable[[str, list[dict[str, Any]], str], str]:
	"""Load YAML prompts and adapt a chat callable returning response text."""
	if not callable(chat_model):
		raise TypeError("chat_model must be callable")
	path = (
		Path(prompt_path)
		if prompt_path is not None
		else Path(__file__).resolve().parents[2]
		/ "config/prompts/orchestrator/orchestrator.yaml"
	)
	prompts = yaml.safe_load(path.read_text(encoding="utf-8"))
	if not isinstance(prompts, Mapping):
		raise ValueError("prompt file must contain a YAML mapping")
	system_prompt = prompts.get("system_prompt")
	user_prompt = prompts.get("user_prompt")
	for name, prompt in (
		("system_prompt", system_prompt), ("user_prompt", user_prompt)
	):
		if not isinstance(prompt, str) or not prompt.strip():
			raise ValueError(f"{name} must be a non-empty string")
	if "{payload}" not in user_prompt:
		raise ValueError("user_prompt must contain {payload}")
	try:
		user_prompt.format(payload="{}")
	except (KeyError, IndexError, ValueError, AttributeError) as error:
		raise ValueError("user_prompt must use only the {payload} placeholder") from error

	def select(query: str, subsystems: list[dict[str, Any]], language: str) -> str:
		payload = json.dumps({
			"query": query, "subsystems": subsystems, "language": language
		})
		return chat_model([
			{"role": "system", "content": system_prompt},
			{"role": "user", "content": user_prompt.format(payload=payload)},
		])

	return select
