from pydantic import BaseModel, ConfigDict, Field

from utils.pipeline.dataclass.models import SubsystemId
from utils.routinemaker.dataclass.models import ROUTINE_PLAN_EXAMPLE, RoutineMakerResult
from utils.exercise_explainer.dataclass.models import ExerciseExplanation


class ChatResponse(BaseModel):
    """Selected subsystem and its text, routine, or database-backed exercise list."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "subsystem": "exercise_explainer",
                "response": (
                    "Stand with your feet shoulder-width apart, brace your core, "
                    "and lower into the squat while keeping your heels grounded."
                )
            }
        }
    )

    subsystem: SubsystemId = Field(
        ...,
        description=(
            "Subsystem ID selected by the orchestrator for this request: "
            "routine_maker, exercise_explainer, past_routines_analyzer, or "
            "no_system when no subsystem can handle the query."
        ),
        examples=[
            "exercise_explainer", "routine_maker", "past_routines_analyzer", "no_system"
        ],
    )

    response: str | RoutineMakerResult | list[ExerciseExplanation] = Field(
        ...,
        description=(
            "Localized text answer, including no-match messages, or a structured "
            "Routine Maker result with status, parameters, message, and routine; "
            "or an exercise list containing original catalog fields and a separate "
            "llm_explanation per exercise. Clarification requests remain text."
        ),
        examples=[
            "Keep your heels grounded and your knees aligned with your toes.",
            {
                "status": "awaiting_confirmation",
                "parameters": {
                    "routine_type": "ppl",
                    "days_per_week": 1,
                    "hours_per_session": 1.0,
                    "level": "beginner",
                },
                "message": "Your draft is ready. Would you like to save it?",
                "routine": ROUTINE_PLAN_EXAMPLE,
                "routine_id": None,
            },
        ],
    )
