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
    """
    return repository.days(user_id)