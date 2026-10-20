"""Expose the user's trailing seven UTC dates and logged-workout flags.

The workout repository distinguishes completed sessions from routine templates
and rejects nonexistent users before constructing the complete calendar.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path as ApiPath

from api.DataClasses.Workout import WorkoutDay
from api.workout_deps import WorkoutRepository, get_workout_repository


router = APIRouter()


@router.get(
    "/users/{user_id}/days",
    response_model=list[WorkoutDay],
    tags=["Users"],
    responses={404: {"description": "The user does not exist."}},
)
def get_user_days(
    user_id: Annotated[int, ApiPath(gt=0)],
    repository: Annotated[WorkoutRepository, Depends(get_workout_repository)],
) -> list[WorkoutDay]:
    """Return seven UTC dates, oldest first, including today.

    has_routine is true when a logged workout exists for that user and date.
    Routine template sets are excluded. Weekday names are in English.

    This GET has no body. The positive user ID selects a profile without
    authentication or ownership authorization.

    Args:
        user_id (int): Positive database user ID from the URL path.
        repository (WorkoutRepository): Injected workout calendar dependency.

    Returns:
        list[WorkoutDay]: HTTP 200 with seven entries, including inactive dates.

    Raises:
        HTTPException: With HTTP 404 when the selected user does not exist.
        Exception: Unhandled persistence/configuration failures become HTTP 500.
            FastAPI rejects invalid path IDs with HTTP 422 before entry.
    """
    # 1. Derive the calendar from completed sets rather than active routine plans.
    return repository.days(user_id)