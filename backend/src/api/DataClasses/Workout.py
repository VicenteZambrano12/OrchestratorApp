"""Define validated workout bodies, persistence receipts, and calendar entries.

The workout API and repository share these models. Request models reject extra
fields and coercion; response models describe recorded sessions rather than
routine templates. No database access or exercise-catalog lookup occurs here.
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkoutSet(BaseModel):
    """Describe one completed exercise set submitted to the workout repository.

    At least one performance measurement is required; weight and effort alone
    cannot establish a completed set. Catalog existence is checked downstream.

    Attributes:
        exercise_id (int): Positive catalog exercise identifier.
        reps (int | None): Positive repetition count, or None.
        weight (float | None): Finite nonnegative weight, or None; this model
            does not convert units.
        duration_seconds (int | None): Positive elapsed seconds, or None.
        distance_meters (float | None): Finite positive distance, or None.
        rpe (float | None): Finite perceived effort from 1 through 10, or None.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    exercise_id: int = Field(gt=0)
    reps: int | None = Field(default=None, gt=0)
    weight: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    duration_seconds: int | None = Field(default=None, gt=0)
    distance_meters: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    rpe: float | None = Field(default=None, ge=1, le=10, allow_inf_nan=False)

    @model_validator(mode="after")
    def require_performance(self) -> "WorkoutSet":
        """Require a performance metric after individual field validation.

        Returns:
            WorkoutSet: This validated instance, with measurements unchanged.

        Raises:
            ValueError: If repetitions, duration, and distance are all absent.
        """
        # 1. Enforce the cross-field completion rule before persistence.
        if self.reps is None and self.duration_seconds is None and self.distance_meters is None:
            raise ValueError("Each set requires reps, duration_seconds, or distance_meters.")
        return self


class WorkoutRequest(BaseModel):
    """Collect completed sets for one user-owned routine.

    The endpoint supplies the user separately; the repository verifies routine
    ownership and catalog IDs before writing the entire collection atomically.

    Attributes:
        routine_id (int): Positive identifier of the routine being performed.
        sets (list[WorkoutSet]): Nonempty ordered collection of completed sets;
            first occurrence establishes exercise order during persistence.
    """

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
    """Report identifiers and timing assigned by the workout repository.

    Returned by the workout endpoint after its transaction commits.

    Attributes:
        training_id (str): Shared generated session identifier for all sets.
        user_id (int): User whose workout was recorded.
        routine_id (int): Referenced routine identifier.
        date (date): UTC calendar date of the recorded session.
        created_at (datetime): Server-generated UTC timestamp for all sets.
        sets_saved (int): Number of inserted set rows.
    """

    training_id: str
    user_id: int
    routine_id: int
    date: date
    created_at: datetime
    sets_saved: int


class WorkoutDay(BaseModel):
    """Represent one UTC day in the repository's seven-day workout calendar.

    The historical field name ``has_routine`` describes logged workouts, not
    whether the user has an active routine or an unperformed template.

    Attributes:
        date (date): Calendar date represented by the entry.
        day_of_week (str): Full English weekday name.
        has_routine (bool): Whether a logged, non-template workout exists.
    """

    date: date
    day_of_week: str = Field(description="Full English weekday name.")
    has_routine: bool = Field(description="Whether the user logged a workout on this UTC date.")
