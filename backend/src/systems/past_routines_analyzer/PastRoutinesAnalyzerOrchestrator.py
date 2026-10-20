"""Expose second-level Gemini routing for SQL-backed workout-history analysis.

YAML supplies route descriptions, system instructions, and a user payload
template. The helper validates conversation memory and model decisions, returning
only an allowed route/filter pair; SQL retrieval occurs later in the workflow.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Final

from obervability.logger import Logger
from utils.general.GeminiApiCall import GeminiClient
from utils.past_routines_analyzer.dataclass.models import PastRoutinesRoute
from utils.past_routines_analyzer.func.load_orchestrator_prompts import (
    load_orchestrator_prompts,
)
from utils.past_routines_analyzer.func.route_request import route_request


logger = Logger.get_logger(__name__)


class PastRoutinesAnalyzerOrchestrator:
    """Use Gemini to choose the sub-task for a workout history request.

    Routes: retrieve a past day's exercises, compare the last two workouts, or
    review performance over the last week. For the first two, Gemini also
    extracts ``day_type`` (e.g. "push", "pull", "leg"), or null for any day.
    Previous conversation turns can be supplied as memory so follow-up
    requests are routed with context.

    Attributes:
        ROUTES (Final[tuple[str, ...]]): Public vocabulary of the three supported
            history tasks; runtime membership also uses the loaded routes map.
        _config (dict[str, Any]): Validated prompts and route descriptions.
        _client (GeminiClient): Injected/default client reused for routing attempts.
    """

    ROUTES: Final[tuple[str, ...]] = (
        "past_day_exercise",
        "compare_last_two_workouts",
        "weekly_performance",
    )

    def __init__(
        self,
        client: GeminiClient | None = None,
        prompt_path: str | Path | None = None,
    ) -> None:
        """Load history-routing configuration and select a reusable client.

        Args:
            client (GeminiClient | None): Existing provider client or default client.
            prompt_path (str | Path | None): Override history-router YAML path.

        Returns:
            None: Initializes routing configuration and the reusable provider client.

        Raises:
            ValueError: Configuration structure or default Gemini settings are invalid.
            OSError: Prompt configuration cannot be read.
            yaml.YAMLError: Prompt configuration cannot be parsed.
        """
        # 1. Separate reusable instructions from request-specific conversation data.
        self._config = load_orchestrator_prompts(prompt_path)
        self._client = GeminiClient() if client is None else client

    def _generate(self, prompt: str, system_prompt: str) -> str:
        """Request one structured routing answer with explicit system instructions.

        Args:
            prompt (str): Formatted user template containing serialized context.
            system_prompt (str): YAML routing policy.

        Returns:
            str: Raw JSON-mode response, validated by the routing retry loop.

        Raises:
            Exception: Provider validation, network, and response failures propagate.
        """
        # 1. JSON output mode guides generation but does not replace schema validation.
        return self._client.generate(
            prompt, system_prompt=system_prompt, response_mime_type="application/json"
        )

    @Logger.trace(logger)
    def route(
        self,
        query: str,
        *,
        language: str = "EN",
        memory: list[Mapping[str, object]] | None = None,
    ) -> PastRoutinesRoute:
        """Return a schema-valid, configured history route and optional day filter.

        Args:
            query (str): Nonblank workout-history request.
            language (str): ``EN`` or ``ES``.
            memory (list[Mapping[str, object]] | None): Prior turns for follow-ups.

        Returns:
            PastRoutinesRoute: Allowed route and normalized day_type.

        Raises:
            ValueError: Input is invalid or three model decisions are rejected.
            pydantic.ValidationError: Prior conversation turns violate their schema.
            Exception: Prompt-formatting and provider failures propagate.
        """
        # 1. Keep context validation and bounded retries in the route helper.
        return route_request(self._generate, self._config, query, language, memory)
