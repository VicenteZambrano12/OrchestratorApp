"""Coordinate Gemini routing, parameterized SQL retrieval, and history explanation.

The nested router uses conversation context to select a static SQL template and
optional day filter. The workflow reads only the requested user's records, then
asks Gemini for prose under a separate YAML system instruction. Returned data
remains the exact SQL rows rather than a model-generated reconstruction.
"""

from collections.abc import Callable, Mapping
from pathlib import Path

from obervability.logger import Logger
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


logger = Logger.get_logger(__name__)


class PastRoutinesWorkflow:
    """Answer a workout history request from the user's logged workouts.

    1. The orchestrator picks the route and day_type (Gemini, 3 attempts).
    2. The route's SQL template is run with SQLClient for the given user.
    3. Gemini explains the rows. ``data`` keeps the exact database rows; only
       ``llm_explain`` is generated.

    Attributes:
        _prompt (str): Validated YAML explanation system instruction.
        _client (GeminiClient): Reused explanation client, shared with the default
            nested router when no router is injected.
        _orchestrator (PastRoutinesAnalyzerOrchestrator): Context-aware route chooser.
        _sql_client_factory (Callable[[], SQLClient]): Creates managed SQL connections.
    """

    def __init__(
        self,
        client: GeminiClient | None = None,
        *,
        orchestrator: PastRoutinesAnalyzerOrchestrator | None = None,
        sql_client_factory: Callable[[], SQLClient] = SQLClient,
        prompt_path: str | Path | None = None,
    ) -> None:
        """Configure reusable routing/explanation dependencies and SQL connection factory.

        Args:
            client (GeminiClient | None): Existing client or a 4096-token default.
            orchestrator (PastRoutinesAnalyzerOrchestrator | None): Injected router,
                or create one sharing this workflow's client.
            sql_client_factory (Callable[[], SQLClient]): Fresh SQL connection factory.
            prompt_path (str | Path | None): Override explanation YAML only; the
                default nested router loads its own routing configuration.

        Returns:
            None: Initializes explanation, routing, and SQL-factory dependencies.

        Raises:
            TypeError: SQL connection factory is not callable.
            ValueError: Prompt contents or default Gemini configuration are invalid.
            OSError: Required prompt configuration cannot be read.
            yaml.YAMLError: Required prompt configuration cannot be parsed.
        """
        # 1. Check the factory before loading instructions or allocating clients.
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

    @Logger.trace(logger)
    def handle(
        self,
        query: str,
        *,
        user_id: int,
        language: str = "EN",
        memory: list[Mapping[str, object]] | None = None,
    ) -> PastRoutinesAnalysis:
        """Route a user-scoped history question and explain its exact retrieved rows.

        Args:
            query (str): Nonblank history question, validated by the nested router.
            user_id (int): Positive account ID; booleans are rejected before I/O.
            language (str): ``EN`` or ``ES`` for routing and explanation.
            memory (list[Mapping[str, object]] | None): Prior turns for routing
                references and explanation context.

        Returns:
            PastRoutinesAnalysis: Validated route/filter, raw rows, and generated
            narrative, including an explanation when retrieval returns no rows.

        Raises:
            ValueError: Input, routing decisions, template, or explanation is invalid.
            pydantic.ValidationError: Memory or final result violates its schema.
            Exception: Configuration, routing, SQL, and provider errors propagate.
        """
        # 1. Reject invalid identity before routing can spend a provider call.
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("user_id must be a positive integer")
        # 2. Resolve follow-ups into a supported retrieval route and optional day type.
        decision = self._orchestrator.route(query, language=language, memory=memory)
        route_labels = {
            "past_day_exercise": "Loading your last training day",
            "compare_last_two_workouts": "Comparing your last two workouts",
            "weekly_performance": "Reviewing your weekly performance",
        }
        report_progress(decision.route, route_labels[decision.route])
        report_progress("history_search", "Searching your logged workout data")
        # 3. Run only the selected static template with bound user/filter values.
        data = fetch_history(self._sql_client_factory, decision, user_id)
        logger.debug("Workout history retrieved row_count=%d", len(data))
        report_progress("history_explanation", "Summarizing your training results")
        # 4. Generate narrative from the rows while preserving the raw data separately.
        explanation = explain_history(
            self._client, self._prompt, query, language, decision, data, memory
        )
        logger.info("Workout history analysis completed route=%s", decision.route)
        # 5. Validate the public envelope instead of trusting provider output shape.
        return PastRoutinesAnalysis(
            route=decision.route,
            day_type=decision.day_type,
            data=data,
            llm_explain=explanation,
        )
