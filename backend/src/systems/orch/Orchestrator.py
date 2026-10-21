"""Expose top-level subsystem selection independently of subsystem execution.

An injected selector can be supplied directly or built from YAML chat prompts
and a reusable Gemini client. The route helper validates request/memory and
configured target IDs, retrying invalid selections up to three times; Pipeline
is responsible for invoking the resulting target.
"""

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from obervability.logger import Logger
from utils.general.GeminiApiCall import GeminiClient
from utils.orch.func.create_chat_selector import create_chat_selector
from utils.orch.func.create_gemini_chat_model import create_gemini_chat_model
from utils.orch.func.no_system_message import no_system_message
from utils.orch.func.resolve_systems_path import resolve_systems_path
from utils.orch.func.route import route


logger = Logger.get_logger(__name__)


class Orchestrator:
	"""Select a subsystem using an injected AI routing function.

	The selector receives the user query, subsystem configurations, and language and
	must return one of their IDs or no_system. This class selects a target; it does not
	invoke the target subsystem.

	Attributes:
		_selector (Callable[..., str]): Query/targets/language adapter, accepting
			an additional memory argument when contextual turns are available.
		_systems_path (Path): Default JSON target catalog used when payloads omit it.
	"""

	def __init__(
		self,
		selector: Callable[..., str],
		systems_path: str | Path | None = None,
	) -> None:
		"""Record the selector and resolve configuration without reading targets.

        Args:
            selector (Callable[..., str]): Routing model adapter.
            systems_path (str | Path | None): Override or packaged target catalog.

        Returns:
            None: Initializes the selector and resolved target-catalog path.

        Raises:
            TypeError: The selector is not callable.
        """
		# 1. Keep dispatch policy injectable while deferring target-file I/O to route.
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
		"""Create a router with separately assembled system and user chat messages.

        Args:
            chat_model (Callable[[list[dict[str, str]]], str]): Chat transport.
            prompt_path (str | Path | None): Override for router YAML instructions.
            systems_path (str | Path | None): Override for the target catalog.

        Returns:
            Orchestrator: Router whose selector captures the validated YAML prompts.

        Raises:
            TypeError: The chat model is not callable.
            ValueError: Required prompt text or template placeholders are invalid.
            OSError: Prompt configuration cannot be read.
            yaml.YAMLError: Prompt configuration cannot be parsed.
        """
		# 1. Assemble the prompt-aware selector once, not on every routing attempt.
		return cls(create_chat_selector(chat_model, prompt_path), systems_path=systems_path)

	@classmethod
	def from_gemini(
		cls,
		client: GeminiClient | None = None,
		prompt_path: str | Path | None = None,
		systems_path: str | Path | None = None,
	) -> "Orchestrator":
		"""Create a YAML-driven router backed by an injected or default Gemini client.

        Args:
            client (GeminiClient | None): Reused client or environment-configured default.
            prompt_path (str | Path | None): Override routing instruction file.
            systems_path (str | Path | None): Override subsystem catalog.

        Returns:
            Orchestrator: Router using Gemini's separate system-instruction channel.

        Raises:
            ValueError: Gemini configuration or prompt contents are invalid.
            OSError: Prompt configuration cannot be read.
            yaml.YAMLError: Prompt configuration cannot be parsed.
        """
		# 1. Adapt the provider to chat first, preserving the same selector contract.
		return cls.from_chat_model(
			create_gemini_chat_model(client),
			prompt_path=prompt_path,
			systems_path=systems_path,
		)

	@staticmethod
	def no_system_message(language: str = "EN") -> str:
		"""Load deterministic guidance for a request with no matching subsystem.

        Args:
            language (str): ``EN`` or ``ES``.

        Returns:
            str: Validated localized fallback from YAML, without an LLM invocation.

        Raises:
            ValueError: Language or fallback configuration is invalid.
            OSError: The fallback file cannot be read.
        """
		# 1. Keep no-match handling independent of provider availability.
		return no_system_message(language)

	@Logger.trace(logger)
	def route(
		self,
		payload: str | Mapping[str, Any],
		language: str | None = None,
	) -> str:
		"""Select an ID after validating input, memory, and exact output membership.

        Args:
            payload (str | Mapping[str, Any]): JSON object/mapping with query and
                optional subsystems, language, and previous conversation turns.
            language (str | None): Override; otherwise use payload language or EN.

        Returns:
            str: Configured subsystem ID or ``no_system``; no subsystem is invoked.

        Raises:
            ValueError: Request/configuration is invalid or three selections fail.
            pydantic.ValidationError: Conversation memory is invalid.
            OSError: A required configuration file cannot be read.
            Exception: Selector/provider failures propagate without fallback dispatch.
        """
		# 1. Centralize validation and retries in the helper shared by all selectors.
		return route(self._selector, self._systems_path, payload, language)
