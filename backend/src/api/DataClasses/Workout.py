from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkoutSet(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    exercise_id: int = Field(gt=0)
    reps: int | None = Field(default=None, gt=0)
    weight: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    duration_seconds: int | None = Field(default=None, gt=0)
    distance_meters: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    rpe: float | None = Field(default=None, ge=1, le=10, allow_inf_nan=False)

    @model_validator(mode="after")
    def require_performance(self) -> "WorkoutSet":
        if self.reps is None and self.duration_seconds is None and self.distance_meters is None:
            raise ValueError("Each set requires reps, duration_seconds, or distance_meters.")
        return self


class WorkoutRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        json_schema_extra={
            "example": {
                "routine_id": 1,
                "sets": [
                    {"exercise_id": 1, "reps": 10, "weight": 40},
                    {"exercise_id": 1, "reps": 8, "weight": 40, "rpe": 8},
                ],
            },
        },
    )

    routine_id: int = Field(gt=0)
    sets: list[WorkoutSet] = Field(min_length=1)


class WorkoutResponse(BaseModel):
    training_id: str
    user_id: int
    routine_id: int
    date: date
    created_at: datetime
    sets_saved: int


class WorkoutDay(BaseModel):
    date: date
    day_of_week: str = Field(description="Full English weekday name.")
    has_routine: bool = Field(description="Whether the user logged a workout on this UTC date.")
