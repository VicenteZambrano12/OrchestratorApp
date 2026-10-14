from dataclasses import dataclass
from typing import Literal

from utils.routinemaker.models import RoutineMakerResult


SubsystemId = Literal[
    "routine_maker", "exercise_explainer", "past_routines_analyzer", "no_system"
]


@dataclass(frozen=True)
class PipelineResult:
    """Selected orchestrator subsystem and its unchanged response payload."""

    subsystem: SubsystemId
    response: str | RoutineMakerResult
