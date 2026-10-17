"""Past routines flow: Gemini routing -> SQL retrieval -> Gemini explanation."""

from collections.abc import Callable, Mapping
from pathlib import Path

from sql.SQLClient import SQLClient
from systems.past_routines_analyzer.PastRoutinesAnalyzerOrchestrator import (
    PastRoutinesAnalyzerOrchestrator,
)
from utils.general.GeminiApiCall import GeminiClient
from utils.pipeline.progress import report_progress
from utils.past_routines_analyzer.dataclass.models import PastRoutinesAnalysis
from utils.past_routines_analyzer.func.explain_history import explain_history
from utils.past_routines_analyzer.func.fetch_history import fetch_history
from utils.past_routines_analyzer.func.load_explainer_prompt import (
    load_explainer_prompt,
)


class PastRoutinesWorkflow:
    """Answer a workout history request from the user's logged workouts.

    1. The orchestrator picks the route and day_type (Gemini, 3 attempts).
    2. The route's SQL template is run with SQLClient for the given user.
    3. Gemini explains the rows. ``data`` keeps the exact database rows; only
       ``llm_explain`` is generated.
    """

    def __init__(
        self,
        client: GeminiClient | None = None,
        *,
        orchestrator: PastRoutinesAnalyzerOrchestrator | None = None,
        sql_client_factory: Callable[[], SQLClient] = SQLClient,
        prompt_path: str | Path | None = None,
    ) -> None:
        if not callable(sql_client_factory):
            raise TypeError("sql_client_factory must be callable")
        self._prompt = load_explainer_prompt(prompt_path)
        self._client = (
            GeminiClient(max_output_tokens=4096) if client is None else client
        )
        self._orchestrator = (
            PastRoutinesAnalyzerOrchestrator(self._client)
            if orchestrator is None
            else orchestrator
        )
        self._sql_client_factory = sql_client_factory

    def handle(
        self,
        query: str,
        *,
        user_id: int,
        language: str = "EN",
        memory: list[Mapping[str, object]] | None = None,
    ) -> PastRoutinesAnalysis:
        """Return the route, day_type, database rows and their explanation.

        Invalid input raises ValueError before any API or database call.
        Routing, database and provider errors propagate.
        """
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id must be a positive integer")
        decision = self._orchestrator.route(query, language=language, memory=memory)
        route_labels = {
            "past_day_exercise": "Loading your last training day",
            "compare_last_two_workouts": "Comparing your last two workouts",
            "weekly_performance": "Reviewing your weekly performance",
        }
        report_progress(decision.route, route_labels[decision.route])
        report_progress("history_search", "Searching your logged workout data")
        data = fetch_history(self._sql_client_factory, decision, user_id)
        report_progress("history_explanation", "Summarizing your training results")
        explanation = explain_history(
            self._client, self._prompt, query, language, decision, data, memory
        )
        return PastRoutinesAnalysis(
            route=decision.route,
            day_type=decision.day_type,
            data=data,
            llm_explain=explanation,
        )
