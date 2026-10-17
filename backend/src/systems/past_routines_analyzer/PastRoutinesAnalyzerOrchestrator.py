"""Second-level Gemini router for past workout analysis requests."""

from collections.abc import Mapping
from pathlib import Path
from typing import Final

from utils.general.GeminiApiCall import GeminiClient
from utils.past_routines_analyzer.dataclass.models import PastRoutinesRoute
from utils.past_routines_analyzer.func.load_orchestrator_prompts import (
    load_orchestrator_prompts,
)
from utils.past_routines_analyzer.func.route_request import route_request


class PastRoutinesAnalyzerOrchestrator:
    """Use Gemini to choose the sub-task for a workout history request.

    Routes: retrieve a past day's exercises, compare the last two workouts, or
    review performance over the last week. For the first two, Gemini also
    extracts ``day_type`` (e.g. "push", "pull", "leg"), or null for any day.
    Previous conversation turns can be supplied as memory so follow-up
    requests are routed with context.
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
        self._config = load_orchestrator_prompts(prompt_path)
        self._client = GeminiClient() if client is None else client

    def _generate(self, prompt: str, system_prompt: str) -> str:
        return self._client.generate(
            prompt, system_prompt=system_prompt, response_mime_type="application/json"
        )

    def route(
        self,
        query: str,
        *,
        language: str = "EN",
        memory: list[Mapping[str, object]] | None = None,
    ) -> PastRoutinesRoute:
        """Return the validated route and day_type.

        Invalid input, or 3 invalid model answers, raise ValueError.
        """
        return route_request(self._generate, self._config, query, language, memory)
