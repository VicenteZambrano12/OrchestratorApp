"""Record completed workout sessions without changing routine selection.

Request models validate measurements; the workout repository verifies the user,
routine ownership, and exercise catalog before inserting all sets atomically.
"""

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

    The JSON body contains a positive routine_id and a nonempty sets list. Each
    set requires a positive exercise_id and at least one of reps, duration_seconds,
    or distance_meters; optional weight and rpe retain their schema constraints.
    No authentication is enforced by this endpoint.

    Args:
        user_id (int): Positive owner profile ID from the URL path.
        workout (WorkoutRequest): Validated JSON routine ID and completed sets.
        repository (WorkoutRepository): Injected transactional persistence layer.

    Returns:
        WorkoutResponse: HTTP 201 with training ID, owner/routine IDs, UTC date
        and timestamp, and inserted set count.

    Raises:
        HTTPException: With HTTP 404 for a nonexistent user, or HTTP 422 for an
            unowned routine or unknown catalog exercises. FastAPI also returns
            422 for invalid path/body input before this function executes.
        Exception: Unhandled database/configuration failures become HTTP 500.
    """
    # 1. Centralize ownership checks and atomic session creation in the repository.
    return repository.save(user_id, workout)
