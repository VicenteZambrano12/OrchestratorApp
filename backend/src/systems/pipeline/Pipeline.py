"""Route user queries and invoke the selected gym system."""

from collections.abc import Mapping

from systems.exercise_explainer.ExerciseExplainer import ExerciseExplainer
from systems.orch.Orchestrator import Orchestrator
from systems.past_routines_analyzer.PastRoutinesAnalyzer import PastRoutinesAnalyzer
from systems.routinemaker.RoutineMaker import RoutineMaker
from utils.routinemaker.models import RoutineMakerResult, RoutineParameters


class Pipeline:
    """Use the same language for routing and the selected system's response."""

    def __init__(
        self,
        orchestrator: Orchestrator | None = None,
        *,
        routine_maker: RoutineMaker | None = None,
        exercise_explainer: ExerciseExplainer | None = None,
        past_routines_analyzer: PastRoutinesAnalyzer | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._routine_maker = routine_maker
        self._exercise_explainer = exercise_explainer
        self._past_routines_analyzer = past_routines_analyzer

    def handle(
        self,
        query: str,
        language: str = "EN",
        *,
        parameters: RoutineParameters | Mapping[str, object] | None = None,
        routine: str | None = None,
        history: str | None = None,
    ) -> str | RoutineMakerResult:
        """Return the selected system's result, or a localized no-match message.

        Dependencies are created on first use and reused on subsequent calls.
        Routine state and history remain caller-owned. Invalid requests,
        unsupported routing IDs, and system/provider errors propagate.
        """
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        if language not in ("ES", "EN"):
            raise ValueError("language must be ES (Spanish) or EN (English)")

        if self._orchestrator is None:
            self._orchestrator = Orchestrator.from_gemini()
        target = self._orchestrator.route({"query": query}, language=language)

        if target == "no_system":
            return self._orchestrator.no_system_message(language)
        if target == "routine_maker":
            if self._routine_maker is None:
                self._routine_maker = RoutineMaker()
            return self._routine_maker.handle(
                query, parameters=parameters, routine=routine, language=language
            )
        if target == "exercise_explainer":
            if self._exercise_explainer is None:
                self._exercise_explainer = ExerciseExplainer()
            return self._exercise_explainer.handle(query, language=language)
        if target == "past_routines_analyzer":
            if self._past_routines_analyzer is None:
                self._past_routines_analyzer = PastRoutinesAnalyzer()
            return self._past_routines_analyzer.handle(
                query, history=history, language=language
            )
        raise ValueError(f"unsupported pipeline subsystem id: {target}")