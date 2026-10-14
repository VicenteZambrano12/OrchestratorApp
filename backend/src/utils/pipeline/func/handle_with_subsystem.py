from collections.abc import Mapping
from typing import TYPE_CHECKING

from systems.exercise_explainer.ExerciseExplainer import ExerciseExplainer
from systems.orch.Orchestrator import Orchestrator
from systems.past_routines_analyzer.PastRoutinesAnalyzer import PastRoutinesAnalyzer
from systems.routinemaker.RoutineMaker import RoutineMaker
from utils.pipeline.dataclass.models import PipelineResult
from utils.routinemaker.dataclass.models import RoutineParameters

if TYPE_CHECKING:
    from systems.pipeline.Pipeline import Pipeline


def handle_with_subsystem(
    pipeline: "Pipeline",
    query: str,
    language: str = "EN",
    *,
    parameters: RoutineParameters | Mapping[str, object] | None = None,
    routine: str | None = None,
    history: str | None = None,
) -> PipelineResult:
    """Route once and execute a system, caching dependencies on the pipeline."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if language not in ("ES", "EN"):
        raise ValueError("language must be ES (Spanish) or EN (English)")

    if pipeline._orchestrator is None:
        pipeline._orchestrator = Orchestrator.from_gemini()
    target = pipeline._orchestrator.route({"query": query}, language=language)

    if target == "no_system":
        return PipelineResult(
            subsystem="no_system",
            response=pipeline._orchestrator.no_system_message(language),
        )
    if target == "routine_maker":
        if pipeline._routine_maker is None:
            pipeline._routine_maker = RoutineMaker()
        return PipelineResult(
            subsystem="routine_maker",
            response=pipeline._routine_maker.handle(
                query, parameters=parameters, routine=routine, language=language
            ),
        )
    if target == "exercise_explainer":
        if pipeline._exercise_explainer is None:
            pipeline._exercise_explainer = ExerciseExplainer()
        return PipelineResult(
            subsystem="exercise_explainer",
            response=pipeline._exercise_explainer.handle(query, language=language),
        )
    if target == "past_routines_analyzer":
        if pipeline._past_routines_analyzer is None:
            pipeline._past_routines_analyzer = PastRoutinesAnalyzer()
        return PipelineResult(
            subsystem="past_routines_analyzer",
            response=pipeline._past_routines_analyzer.handle(
                query, history=history, language=language
            ),
        )
    raise ValueError(f"unsupported pipeline subsystem id: {target}")
