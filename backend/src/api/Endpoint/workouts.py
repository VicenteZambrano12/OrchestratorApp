from typing import Annotated

from fastapi import APIRouter, Depends, Path as ApiPath

from api.DataClasses.Workout import WorkoutRequest, WorkoutResponse
from api.workout_deps import WorkoutRepository, get_workout_repository


router = APIRouter()


@router.post(
    "/users/{user_id}/workouts",
    status_code=201,
    response_model=WorkoutResponse,
    tags=["Users"],
    responses={
        404: {"description": "The user does not exist."},
        422: {"description": "Invalid workout, unknown exercise, or routine not owned by this user."},
    },
)
def save_workout(
    user_id: Annotated[int, ApiPath(gt=0)],
    workout: WorkoutRequest,
    repository: Annotated[WorkoutRepository, Depends(get_workout_repository)],
) -> WorkoutResponse:
    """Save completed sets atomically with a shared session ID and server UTC date.

    Exercise order follows first appearance; set numbers increment per exercise.
    This records a new session on each call and does not change the active routine.
    """
    return repository.save(user_id, workout)
