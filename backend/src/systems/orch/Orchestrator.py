from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from utils.general.GeminiApiCall import GeminiClient
from utils.orch.func.create_chat_selector import create_chat_selector
from utils.orch.func.create_gemini_chat_model import create_gemini_chat_model
from utils.orch.func.no_system_message import no_system_message
from utils.orch.func.resolve_systems_path import resolve_systems_path
from utils.orch.func.route import route


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
		self._systems_path = resolve_systems_path(systems_path)

	@classmethod
	def from_chat_model(
		cls,
		chat_model: Callable[[list[dict[str, str]]], str],
		prompt_path: str | Path | None = None,
		systems_path: str | Path | None = None,
	) -> "Orchestrator":
		"""Load YAML prompts and adapt a chat callable returning response text."""
		return cls(create_chat_selector(chat_model, prompt_path), systems_path=systems_path)

	@classmethod
	def from_gemini(
		cls,
		client: GeminiClient | None = None,
		prompt_path: str | Path | None = None,
		systems_path: str | Path | None = None,
	) -> "Orchestrator":
		"""Route with Gemini using YAML prompts and environment configuration."""
		return cls.from_chat_model(
			create_gemini_chat_model(client),
			prompt_path=prompt_path,
			systems_path=systems_path,
		)

	@staticmethod
	def no_system_message(language: str = "EN") -> str:
		"""Load the user-facing no-match message for the requested language."""
		return no_system_message(language)

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
		return route(self._selector, self._systems_path, payload, language)
