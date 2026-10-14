from dataclasses import dataclass
from typing import Literal

from utils.routinemaker.dataclass.models import RoutineMakerResult
from utils.exercise_explainer.dataclass.models import ExerciseExplanation


SubsystemId = Literal[
    "routine_maker", "exercise_explainer", "past_routines_analyzer", "no_system"
]


@dataclass(frozen=True)
class PipelineResult:
    """Selected orchestrator subsystem and its unchanged response payload."""

    subsystem: SubsystemId
    response: str | RoutineMakerResult | list[ExerciseExplanation]
