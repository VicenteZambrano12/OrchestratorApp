"""Build a reusable selector from YAML instructions and a chat transport.

Instructions remain a system message; serialized query, subsystem descriptions,
language, and optional memory form the user message. This adapter does not
validate the selected ID: the routing loop owns that boundary.
"""

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import yaml

from obervability.logger import Logger


logger = Logger.get_logger(__name__)


@Logger.trace(logger)
def create_chat_selector(
	chat_model: Callable[[list[dict[str, str]]], str],
	prompt_path: str | Path | None = None,
) -> Callable[[str, list[dict[str, Any]], str], str]:
	"""Load routing instructions and close over a validated user template.

    Args:
        chat_model (Callable[[list[dict[str, str]]], str]): Chat transport.
        prompt_path (str | Path | None): YAML override, or packaged router prompts.

    Returns:
        Callable: Selector accepting query, subsystem dictionaries, language,
            and optional memory, and returning the transport's raw text.

    Raises:
        TypeError: The transport is not callable.
        ValueError: YAML structure or the sole ``{payload}`` placeholder is invalid.
        OSError: The prompt file cannot be read.
        yaml.YAMLError: The prompt file cannot be parsed.
    """
	# 1. Validate reusable configuration before any request can reach the model.
	if not callable(chat_model):
		raise TypeError("chat_model must be callable")
	path = (
		Path(prompt_path)
		if prompt_path is not None
		else Path(__file__).resolve().parents[3]
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

	def select(
		query: str,
		subsystems: list[dict[str, Any]],
		language: str,
		memory: list[dict[str, object]] | None = None,
	) -> str:
		"""Assemble routing context without promoting user data to instructions.

        Args:
            query (str): User request to classify.
            subsystems (list[dict[str, Any]]): Allowed target descriptions.
            language (str): Requested response language.
            memory (list[dict[str, object]] | None): Prior validated turns.

        Returns:
            str: Unvalidated model selection for the outer retry loop.

        Raises:
            TypeError: Payload values cannot be JSON serialized.
            Exception: Transport/provider failures propagate without retry here.
        """
		# 1. Keep history and target descriptions in the serialized request context.
		data: dict[str, Any] = {
			"query": query, "subsystems": subsystems, "language": language
		}
		if memory:
			data["memory"] = memory
		payload = json.dumps(data)
		# 2. Inject YAML instructions separately from the formatted user payload.
		return chat_model([
			{"role": "system", "content": system_prompt},
			{"role": "user", "content": user_prompt.format(payload=payload)},
		])

	return select
