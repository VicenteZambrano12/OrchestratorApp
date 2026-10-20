"""Dispatch one validated query through the top-level router and chosen system.

Dependencies are initialized lazily on the Pipeline instance and reused. Memory
informs routing and contextual explanation/history requests; routine state uses
session/user identity instead. ``no_system`` is deterministic localized guidance,
not an invitation to execute an unknown subsystem.
"""

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
    """Validate the request, select a target, and execute only that target.

    Args:
        pipeline (Pipeline): Owner of lazy/reusable subsystem instances.
        query (str): Nonblank current request.
        language (str): Shared ``EN`` or ``ES`` routing/response language.
        parameters (RoutineParameters | Mapping[str, object] | None): Routine
            parameter overrides, forwarded only to RoutineMaker.
        routine (RoutinePlan | None): Optional routine draft override.
        memory (list[dict[str, object]] | None): Prior turns for model context.
        session_id (str | None): Required session scope for routine drafts.
        user_id (int | None): Required user scope for routine or history requests.
        client_saves_routine (bool): Defer confirmed routine persistence to client.

    Returns:
        PipelineResult: Exact target ID and unchanged subsystem response.

    Raises:
        ValueError: Query/language is invalid or the selected ID is unsupported.
        RoutineInputError: A routine/history target lacks required identity.
        Exception: Routing, configuration, provider, store, and SQL errors propagate.
    """
    # 1. Reject invalid shared inputs before routing or allocating subsystem clients.
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if language not in ("ES", "EN"):
        raise ValueError("language must be ES (Spanish) or EN (English)")

    # 2. Route with optional prior turns; keep target execution outside the router.
    report_progress("orchestrator", "Analyzing your request")
    if pipeline._orchestrator is None:
        pipeline._orchestrator = Orchestrator.from_gemini()
    payload: dict[str, object] = {"query": query}
    if memory:
        payload["memory"] = memory
    target = pipeline._orchestrator.route(payload, language=language)

    # 3. A no-match decision uses configured guidance without another model call.
    if target == "no_system":
        report_progress("general_guidance", "Preparing general guidance")
        return PipelineResult(
            subsystem="no_system",
            response=pipeline._orchestrator.no_system_message(language),
        )
    # 4. Routine execution requires both identity scopes for its persisted draft.
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
    # 5. Exercise follow-ups use conversation memory, then resolve catalog facts.
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
    # 6. History retrieval is user-scoped; its nested router also receives memory.
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
    # 7. Fail closed if a custom router returns an ID with no executable adapter.
    raise ValueError(f"unsupported pipeline subsystem id: {target}")
