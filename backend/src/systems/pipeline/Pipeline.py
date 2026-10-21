"""Coordinate contextual subsystem dispatch and successful-turn persistence.

The pipeline loads recent session turns for routing, delegates one target's
execution, and returns native subsystem results. Successful turns are stored in
compact form for future requests: routine structure is retained, history keeps
only its explanation, and other structured results are JSON serialized.
"""

import json
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

from pydantic import BaseModel

from obervability.logger import Logger
from systems.exercise_explainer.ExerciseExplainer import ExerciseExplainer
from systems.orch.Orchestrator import Orchestrator
from systems.past_routines_analyzer.PastRoutinesWorkflow import PastRoutinesWorkflow
from systems.routinemaker.RoutineMaker import RoutineMaker
from utils.pipeline.dataclass.models import PipelineResult
from utils.pipeline.func.handle_with_subsystem import handle_with_subsystem
from utils.routinemaker.dataclass.models import RoutineMakerResult, RoutineParameters, RoutinePlan
from utils.exercise_explainer.dataclass.models import ExerciseExplanation
from utils.past_routines_analyzer.dataclass.models import PastRoutinesAnalysis


logger = Logger.get_logger(__name__)


def _dump_model(value: Any) -> Any:
    """Convert supported structured responses for conversation-memory JSON.

    Args:
        value (Any): Object passed by ``json.dumps`` after native encoding fails.

    Returns:
        Any: JSON-mode Pydantic dictionary or recursively converted dataclass data.

    Raises:
        TypeError: The value is neither a model nor a dataclass instance.
    """
    # 1. Preserve structured response content without serializing arbitrary objects.
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


class Pipeline:
    """Use one language for routing and execution with optional session memory.

    Attributes:
        _orchestrator (Orchestrator | None): Router, created lazily when absent.
        _routine_maker (RoutineMaker | None): Reusable routine subsystem.
        _exercise_explainer (ExerciseExplainer | None): Reusable catalog explainer.
        _past_routines_analyzer (PastRoutinesWorkflow | None): Reusable SQL-history
            workflow. All absent subsystem dependencies are created on first use.
        _turn_setter (Any | None): Optional persistence adapter exposing ``set``.
        _turn_getter (Any | None): Optional history adapter exposing ``get``.
        _memory_turns (int): Maximum recent-turn count requested from the getter.

    Routine draft state remains session/user-scoped inside RoutineMaker rather
    than being reconstructed solely from conversational text.
    """

    def __init__(
        self,
        orchestrator: Orchestrator | None = None,
        *,
        routine_maker: RoutineMaker | None = None,
        exercise_explainer: ExerciseExplainer | None = None,
        past_routines_analyzer: PastRoutinesWorkflow | None = None,
        turn_setter: Any | None = None,
        turn_getter: Any | None = None,
        memory_turns: int = 2,
    ) -> None:
        """Record injectable dependencies without eagerly constructing subsystems.

        Args:
            orchestrator (Orchestrator | None): Router or lazy Gemini-backed default.
            routine_maker (RoutineMaker | None): Routine workflow override.
            exercise_explainer (ExerciseExplainer | None): Exercise workflow override.
            past_routines_analyzer (PastRoutinesWorkflow | None): History override.
            turn_setter (Any | None): Adapter storing successful conversation turns.
            turn_getter (Any | None): Adapter reading recent session turns.
            memory_turns (int): Turn count forwarded unchanged to the getter.

        Returns:
            None: Records dependencies and memory settings for lazy dispatch.
        """
        # 1. Keep construction side-effect-free; dispatch chooses which clients are needed.
        self._orchestrator = orchestrator
        self._routine_maker = routine_maker
        self._exercise_explainer = exercise_explainer
        self._past_routines_analyzer = past_routines_analyzer
        self._turn_setter = turn_setter
        self._turn_getter = turn_getter
        self._memory_turns = memory_turns

    def handle(
        self,
        query: str,
        language: str = "EN",
        *,
        parameters: RoutineParameters | Mapping[str, object] | None = None,
        routine: RoutinePlan | None = None,
        session_id: str | None = None,
        user_id: int | None = None,
        client_saves_routine: bool = False,
    ) -> str | RoutineMakerResult | list[ExerciseExplanation] | PastRoutinesAnalysis:
        """Return a native subsystem response without its dispatch envelope.

        Dependencies are lazy and reused. Routine drafts require session/user
        identity; SQL-backed history requires user identity.

        Args:
            query (str): Nonblank current request.
            language (str): ``EN`` or ``ES`` shared by routing and execution.
            parameters (RoutineParameters | Mapping[str, object] | None): Routine
                requirement overrides.
            routine (RoutinePlan | None): Optional explicit routine draft.
            session_id (str | None): Conversation scope and required routine scope.
            user_id (int | None): Account scope for routine/history operations.
            client_saves_routine (bool): Defer confirmed routine saves to the client.

        Returns:
            str | RoutineMakerResult | list[ExerciseExplanation] |
            PastRoutinesAnalysis: Unchanged subsystem output or localized fallback.

        Raises:
            ValueError: Request or routing target is invalid.
            RoutineInputError: The selected workflow lacks required identity.
            Exception: Memory, configuration, validation, provider, or SQL failures
                propagate from the enveloped operation.
        """
        # 1. Share the full memory/dispatch/persistence path, dropping only its envelope.
        return self.handle_with_subsystem(
            query,
            language,
            parameters=parameters,
            routine=routine,
            session_id=session_id,
            user_id=user_id,
            **({"client_saves_routine": True} if client_saves_routine else {}),
        ).response

    @Logger.trace(logger)
    def handle_with_subsystem(
        self,
        query: str,
        language: str = "EN",
        *,
        parameters: RoutineParameters | Mapping[str, object] | None = None,
        routine: RoutinePlan | None = None,
        session_id: str | None = None,
        user_id: int | None = None,
        client_saves_routine: bool = False,
    ) -> PipelineResult:
        """Route once, execute the target, and persist an optional successful turn.

        A no-match answer uses ``no_system``. Turn persistence happens only after
        dispatch succeeds, and store failures still propagate to the caller.

        Args:
            query (str): Nonblank user request.
            language (str): ``EN`` or ``ES`` for the router and selected subsystem.
            parameters (RoutineParameters | Mapping[str, object] | None): Routine
                requirement overrides.
            routine (RoutinePlan | None): Optional explicit routine draft.
            session_id (str | None): Recent-turn scope and required routine scope.
            user_id (int | None): Required account scope for routines/history.
            client_saves_routine (bool): Defer confirmed routine persistence.

        Returns:
            PipelineResult: Selected subsystem and its unchanged native response.

        Raises:
            ValueError: Request, router output, or subsystem data is invalid.
            RoutineInputError: Routine/history identity requirements are unmet.
            TypeError: A stored structured response cannot be JSON serialized.
            Exception: Memory-store, configuration, provider, or SQL errors
                propagate; no synthetic success response is substituted.
        """
        # 1. Retrieve only recent session turns; preserve the getter's iteration order.
        memory = None
        if session_id is not None and self._turn_getter is not None:
            memory = list(
                self._turn_getter.get(session_id, self._memory_turns).values()
            )
        # 2. Delegate shared validation and one target execution with this turn's context.
        result = handle_with_subsystem(
            self,
            query,
            language,
            parameters=parameters,
            routine=routine,
            memory=memory,
            session_id=session_id,
            user_id=user_id,
            **({"client_saves_routine": True} if client_saves_routine else {}),
        )
        # 3. Persist compact successful context, not a second generated interpretation.
        if session_id is not None and self._turn_setter is not None:
            response = result.response
            if isinstance(response, RoutineMakerResult):
                self._turn_setter.set(
                    session_id, query, response.message, result.subsystem,
                    routine=response.routine.model_dump(mode="json") if response.routine else None,
                )
            elif isinstance(response, PastRoutinesAnalysis):
                # Keep only prose here: raw history rows would bloat future routing prompts.
                self._turn_setter.set(
                    session_id, query, response.llm_explain, result.subsystem
                )
            else:
                if not isinstance(response, str):
                    response = json.dumps(response, default=_dump_model)
                self._turn_setter.set(session_id, query, response, result.subsystem)
        logger.info("Pipeline completed subsystem=%s", result.subsystem)
        return result