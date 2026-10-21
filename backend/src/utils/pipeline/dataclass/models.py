"""Define the pipeline's immutable dispatch envelope and supported target IDs.

Responses remain native subsystem values rather than being coerced into a
single generated string. The outer pipeline separately serializes conversation
memory, so returning structured data does not force it into future prompts.
"""

from dataclasses import dataclass
from typing import Literal

from utils.routinemaker.dataclass.models import RoutineMakerResult
from utils.exercise_explainer.dataclass.models import ExerciseExplanation
from utils.past_routines_analyzer.dataclass.models import PastRoutinesAnalysis


SubsystemId = Literal[
    "routine_maker", "exercise_explainer", "past_routines_analyzer", "no_system"
]


@dataclass(frozen=True)
class PipelineResult:
    """Pair a dispatch decision with its unchanged subsystem result.

    Attributes:
        subsystem (SubsystemId): ``routine_maker``, ``exercise_explainer``,
            ``past_routines_analyzer``, or reserved ``no_system``.
        response (str | RoutineMakerResult | list[ExerciseExplanation] |
            PastRoutinesAnalysis): Clarification/fallback text or structured
            subsystem output. Frozen fields prevent envelope reassignment, not
            mutation of objects held inside the response.
    """

    subsystem: SubsystemId
    response: str | RoutineMakerResult | list[ExerciseExplanation] | PastRoutinesAnalysis
