"""Route user queries and invoke the selected gym system."""

from collections.abc import Mapping

from systems.exercise_explainer.ExerciseExplainer import ExerciseExplainer
from systems.orch.Orchestrator import Orchestrator
from systems.past_routines_analyzer.PastRoutinesAnalyzer import PastRoutinesAnalyzer
from systems.routinemaker.RoutineMaker import RoutineMaker
from utils.pipeline.dataclass.models import PipelineResult
from utils.pipeline.func.handle_with_subsystem import handle_with_subsystem
from utils.routinemaker.dataclass.models import RoutineMakerResult, RoutineParameters


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
        return self.handle_with_subsystem(
            query,
            language,
            parameters=parameters,
            routine=routine,
            history=history,
        ).response

    def handle_with_subsystem(
        self,
        query: str,
        language: str = "EN",
        *,
        parameters: RoutineParameters | Mapping[str, object] | None = None,
        routine: str | None = None,
        history: str | None = None,
    ) -> PipelineResult:
        """Route once and return the selected subsystem with its unchanged result.

        A no-match answer uses the reserved `no_system` ID. Dependencies remain
        lazy and reusable; routine state and history remain caller-owned.
        Validation, routing, provider, and system failures propagate unchanged.
        """
        return handle_with_subsystem(
            self,
            query,
            language,
            parameters=parameters,
            routine=routine,
            history=history,
        )