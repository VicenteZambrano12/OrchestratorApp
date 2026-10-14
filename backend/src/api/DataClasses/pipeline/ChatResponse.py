from pydantic import BaseModel, ConfigDict, Field

from utils.pipeline.dataclass.models import SubsystemId
from utils.routinemaker.dataclass.models import RoutineMakerResult


class ChatResponse(BaseModel):
    """Selected subsystem and its localized answer or structured routine result."""

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

    response: str | RoutineMakerResult = Field(
        ...,
        description=(
            "Localized text answer, including no-match messages, or a structured "
            "Routine Maker result with status, parameters, message, and routine."
        ),
        examples=[
            "Keep your heels grounded and your knees aligned with your toes.",
            {
                "status": "created",
                "parameters": {
                    "routine_type": "ppl",
                    "days_per_week": 3,
                    "hours_per_session": 1.0,
                    "level": "beginner",
                },
                "message": "Your three-day push/pull/legs routine is ready.",
                "routine": (
                    "Day 1 - Push: bench press, overhead press, triceps extensions.\n"
                    "Day 2 - Pull: lat pulldown, seated row, biceps curls.\n"
                    "Day 3 - Legs: squat, Romanian deadlift, calf raises."
                ),
            },
        ],
    )
