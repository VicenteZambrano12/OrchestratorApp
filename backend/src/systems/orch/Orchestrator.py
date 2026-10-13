import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, StrictStr, ValidationError, ValidationInfo, field_validator

from utils.general.GeminiApiCall import GeminiClient


class _RoutingSelection(BaseModel):
	selected_id: StrictStr

	@field_validator("selected_id")
	@classmethod
	def validate_selected_id(cls, value: str, info: ValidationInfo) -> str:
		if info.context is None or value not in info.context["allowed_ids"]:
			raise ValueError("selection must be exactly one allowed routing id")
		return value


class Orchestrator:
	"""Select a subsystem using an injected AI routing function.

	The selector receives the user query, subsystem configurations, and language and
	must return one of their IDs or no_system. This class selects a target; it does not
	invoke the target subsystem.
	"""

	def __init__(
		self,
		selector: Callable[[str, list[dict[str, Any]], str], str],
		systems_path: str | Path | None = None,
	) -> None:
		if not callable(selector):
			raise TypeError("selector must be callable")
		self._selector = selector
		self._systems_path = (
			Path(systems_path)
			if systems_path is not None
			else Path(__file__).resolve().parents[2] / "config/systems.json"
		)

	@classmethod
	def from_chat_model(
		cls,
		chat_model: Callable[[list[dict[str, str]]], str],
		prompt_path: str | Path | None = None,
		systems_path: str | Path | None = None,
	) -> "Orchestrator":
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

		return cls(select, systems_path=systems_path)

	@classmethod
	def from_gemini(
		cls,
		client: GeminiClient | None = None,
		prompt_path: str | Path | None = None,
		systems_path: str | Path | None = None,
	) -> "Orchestrator":
		"""Route with Gemini using YAML prompts and environment configuration."""
		gemini_client = GeminiClient() if client is None else client

		def chat_model(messages: list[dict[str, str]]) -> str:
			return gemini_client.generate(
				messages[1]["content"], system_prompt=messages[0]["content"]
			).strip()

		return cls.from_chat_model(
			chat_model, prompt_path=prompt_path, systems_path=systems_path
		)

	@staticmethod
	def no_system_message(language: str = "EN") -> str:
		"""Load the user-facing no-match message for the requested language."""
		if language not in ("ES", "EN"):
			raise ValueError("language must be ES (Spanish) or EN (English)")
		path = (
			Path(__file__).resolve().parents[2]
			/ "config/prompts/nosystem/nosystem.yaml"
		)
		try:
			configuration = yaml.safe_load(path.read_text(encoding="utf-8"))
		except yaml.YAMLError as error:
			raise ValueError("invalid no_system message YAML") from error
		if not isinstance(configuration, Mapping):
			raise ValueError("no_system message file must contain a YAML mapping")
		messages = configuration.get("messages")
		if not isinstance(messages, Mapping):
			raise ValueError("no_system message file must contain a messages mapping")
		message = messages.get(language)
		if not isinstance(message, str) or not message.strip():
			raise ValueError(f"no_system message for {language} must be a non-empty string")
		return message

	def route(
		self,
		payload: str | Mapping[str, Any],
		language: str | None = None,
	) -> str:
		"""Route a query, loading configured subsystems when omitted from JSON.

		Return only the selected subsystem ID, or no_system if none matches.
		Validate selections with Pydantic, allowing three total attempts.
		Invalid input or three invalid selections raises ValueError.
		Selector failures and configuration file errors propagate to the caller.
		"""
		if isinstance(payload, str):
			payload = json.loads(payload)
		if not isinstance(payload, Mapping):
			raise ValueError("payload must be a JSON object")

		query = payload.get("query")
		if not isinstance(query, str) or not query.strip():
			raise ValueError("query must be a non-empty string")
		if language is None:
			language = payload.get("language", "EN")
		if not isinstance(language, str) or language not in ("ES", "EN"):
			raise ValueError("language must be ES (Spanish) or EN (English)")

		if "subsystems" in payload:
			subsystems = payload["subsystems"]
		else:
			configuration = json.loads(self._systems_path.read_text(encoding="utf-8"))
			if not isinstance(configuration, Mapping):
				raise ValueError("systems configuration must be a JSON object")
			subsystems = configuration.get("subsystems")
		if not isinstance(subsystems, list) or not subsystems:
			raise ValueError("subsystems must be a non-empty list")

		targets: dict[str, dict[str, Any]] = {}
		for subsystem in subsystems:
			if not isinstance(subsystem, Mapping):
				raise ValueError("each subsystem must be a JSON object")
			subsystem_id = subsystem.get("id")
			description = subsystem.get("description")
			if not isinstance(subsystem_id, str) or not subsystem_id.strip():
				raise ValueError("each subsystem must have a non-empty string id")
			if not isinstance(description, str) or not description.strip():
				raise ValueError(
					"each subsystem must have a non-empty string description"
				)
			if subsystem_id in targets:
				raise ValueError(f"duplicate subsystem id: {subsystem_id}")
			targets[subsystem_id] = dict(subsystem)

		allowed_ids = set(targets) | {"no_system"}
		last_error: ValidationError | None = None
		for _ in range(3):
			selected_id = self._selector(
				query, [dict(target) for target in targets.values()], language
			)
			try:
				selection = _RoutingSelection.model_validate(
					{"selected_id": selected_id}, context={"allowed_ids": allowed_ids}
				)
			except ValidationError as error:
				last_error = error
			else:
				return selection.selected_id
		raise ValueError(
			"selector failed to return exactly one allowed routing id "
			f"after 3 attempts; allowed ids: {', '.join(sorted(allowed_ids))}"
		) from last_error
