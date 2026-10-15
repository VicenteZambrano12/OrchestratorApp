from collections.abc import Mapping
from typing import TYPE_CHECKING

from systems.exercise_explainer.ExerciseExplainer import ExerciseExplainer
from systems.orch.Orchestrator import Orchestrator
from systems.past_routines_analyzer.PastRoutinesWorkflow import PastRoutinesWorkflow
from systems.routinemaker.RoutineMaker import RoutineMaker
from utils.pipeline.dataclass.models import PipelineResult
from utils.pipeline.progress import report_progress
from utils.routinemaker.dataclass.models import RoutineParameters, RoutinePlan
from utils.routinemaker.func.repository import RoutineInputError

if TYPE_CHECKING:
    from systems.pipeline.Pipeline import Pipeline


def handle_with_subsystem(
    pipeline: "Pipeline",
    query: str,
    language: str = "EN",
    *,
    parameters: RoutineParameters | Mapping[str, object] | None = None,
    routine: RoutinePlan | None = None,
    memory: list[dict[str, object]] | None = None,
    session_id: str | None = None,
    user_id: int | None = None,
    client_saves_routine: bool = False,
) -> PipelineResult:
    """Route once and execute a system, caching dependencies on the pipeline."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if language not in ("ES", "EN"):
        raise ValueError("language must be ES (Spanish) or EN (English)")

    report_progress("orchestrator", "Analyzing your request")
    if pipeline._orchestrator is None:
        pipeline._orchestrator = Orchestrator.from_gemini()
    payload: dict[str, object] = {"query": query}
    if memory:
        payload["memory"] = memory
    target = pipeline._orchestrator.route(payload, language=language)

    if target == "no_system":
        report_progress("general_guidance", "Preparing general guidance")
        return PipelineResult(
            subsystem="no_system",
            response=pipeline._orchestrator.no_system_message(language),
        )
    if target == "routine_maker":
        if user_id is None:
            raise RoutineInputError("Routine requests require user_id.")
        if session_id is None:
            raise RoutineInputError("Routine requests require session_id.")
        report_progress("routine_maker", "Planning your routine request")
        if pipeline._routine_maker is None:
            pipeline._routine_maker = RoutineMaker()
        return PipelineResult(
            subsystem="routine_maker",
            response=pipeline._routine_maker.handle(
                query, parameters=parameters, routine=routine, language=language,
                session_id=session_id, user_id=user_id,
                **({"client_saves_routine": True} if client_saves_routine else {}),
            ),
        )
    if target == "exercise_explainer":
        report_progress("exercise_explainer", "Identifying the exercises to explain")
        if pipeline._exercise_explainer is None:
            pipeline._exercise_explainer = ExerciseExplainer()
        return PipelineResult(
            subsystem="exercise_explainer",
            response=pipeline._exercise_explainer.handle(
                query, language=language, **({"memory": memory} if memory else {})
            ),
        )
    if target == "past_routines_analyzer":
        if user_id is None:
            raise RoutineInputError("Past routine requests require user_id.")
        report_progress("past_routines_analyzer", "Choosing how to review your training history")
        if pipeline._past_routines_analyzer is None:
            pipeline._past_routines_analyzer = PastRoutinesWorkflow()
        return PipelineResult(
            subsystem="past_routines_analyzer",
            response=pipeline._past_routines_analyzer.handle(
                query, user_id=user_id, language=language,
                **({"memory": memory} if memory else {}),
            ),
        )
    raise ValueError(f"unsupported pipeline subsystem id: {target}")
