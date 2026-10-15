"""Route user queries and invoke the selected gym system."""

import json
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

from pydantic import BaseModel

from systems.exercise_explainer.ExerciseExplainer import ExerciseExplainer
from systems.orch.Orchestrator import Orchestrator
from systems.past_routines_analyzer.PastRoutinesAnalyzer import PastRoutinesAnalyzer
from systems.routinemaker.RoutineMaker import RoutineMaker
from utils.pipeline.dataclass.models import PipelineResult
from utils.pipeline.func.handle_with_subsystem import handle_with_subsystem
from utils.routinemaker.dataclass.models import RoutineMakerResult, RoutineParameters, RoutinePlan
from utils.exercise_explainer.dataclass.models import ExerciseExplanation


def _dump_model(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


class Pipeline:
    """Use the same language for routing and the selected system's response."""

    def __init__(
        self,
        orchestrator: Orchestrator | None = None,
        *,
        routine_maker: RoutineMaker | None = None,
        exercise_explainer: ExerciseExplainer | None = None,
        past_routines_analyzer: PastRoutinesAnalyzer | None = None,
        turn_setter: Any | None = None,
        turn_getter: Any | None = None,
        memory_turns: int = 2,
    ) -> None:
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
        history: str | None = None,
        session_id: str | None = None,
        user_id: int | None = None,
    ) -> str | RoutineMakerResult | list[ExerciseExplanation]:
        """Return the selected system's result, or a localized no-match message.

        Dependencies are created on first use and reused on subsequent calls.
        Routine drafts are cached per session/user; analyzer history is caller-owned. Invalid requests,
        unsupported routing IDs, and system/provider errors propagate.
        """
        return self.handle_with_subsystem(
            query,
            language,
            parameters=parameters,
            routine=routine,
            history=history,
            session_id=session_id,
            user_id=user_id,
        ).response

    def handle_with_subsystem(
        self,
        query: str,
        language: str = "EN",
        *,
        parameters: RoutineParameters | Mapping[str, object] | None = None,
        routine: RoutinePlan | None = None,
        history: str | None = None,
        session_id: str | None = None,
        user_id: int | None = None,
    ) -> PipelineResult:
        """Route once and return the selected subsystem with its unchanged result.

        A no-match answer uses the reserved `no_system` ID. Dependencies remain
        lazy and reusable; routine drafts are session/user-scoped and history is caller-owned.
        Validation, routing, provider, and system failures propagate unchanged.
        When `session_id` and a turn setter are provided, the turn is stored
        after a successful result.
        """
        memory = None
        if session_id is not None and self._turn_getter is not None:
            memory = list(
                self._turn_getter.get(session_id, self._memory_turns).values()
            )
        result = handle_with_subsystem(
            self,
            query,
            language,
            parameters=parameters,
            routine=routine,
            history=history,
            memory=memory,
            session_id=session_id,
            user_id=user_id,
        )
        if session_id is not None and self._turn_setter is not None:
            response = result.response
            if isinstance(response, RoutineMakerResult):
                self._turn_setter.set(
                    session_id, query, response.message, result.subsystem,
                    routine=response.routine.model_dump(mode="json") if response.routine else None,
                )
            else:
                if not isinstance(response, str):
                    response = json.dumps(response, default=_dump_model)
                self._turn_setter.set(session_id, query, response, result.subsystem)
        return result