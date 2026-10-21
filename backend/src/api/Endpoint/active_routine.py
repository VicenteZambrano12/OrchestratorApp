"""Retrieve the selected saved routine, including supported legacy templates.

The repository owns user validation and stored-format decoding. The endpoint
adds the database routine ID as a response header without changing the plan
payload or invoking generation, prompts, or tools.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path as ApiPath, Response

from utils.routinemaker.dataclass.models import LegacyRoutinePlan, RoutinePlan
from utils.routinemaker.func.repository import (
    RoutineDataError,
    RoutineInputError,
    RoutineRepository,
)


router = APIRouter()


def get_routine_repository() -> RoutineRepository:
    """Create a routine repository using runtime database configuration.

    Returns:
        RoutineRepository: Persistence dependency for routine reads and writes.
    """
    # 1. Defer runtime database access to the injected repository's operations.
    return RoutineRepository()


@router.get(
    "/users/{user_id}/routine", response_model=RoutinePlan | LegacyRoutinePlan | None, tags=["Users"],
    responses={
        200: {"headers": {"X-Routine-Id": {
            "description": "Database ID of the returned routine; absent when no routine exists.",
            "schema": {"type": "integer"},
        }}},
        404: {"description": "The user does not exist."},
        409: {"description": "The active routine uses an unsupported stored format."},
    },
)
def get_active_routine(
    user_id: Annotated[int, ApiPath(gt=0)],
    response: Response,
    repository: Annotated[RoutineRepository, Depends(get_routine_repository)],
):
    """Return the user's active saved routine, or null when they have none.

    This GET has no request body. Modern plans and supported legacy workout
    templates retain their respective response formats. A returned plan includes
    its database ID in ``X-Routine-Id``; a null response has no such header.
    The caller-selected user scope is not authentication.

    Args:
        user_id (int): Positive database user ID from the path.
        response (Response): FastAPI response carrying the routine-ID header.
        repository (RoutineRepository): Injected storage and decoding dependency.

    Returns:
        RoutinePlan | LegacyRoutinePlan | None: HTTP 200 plan or JSON null.

    Raises:
        HTTPException: With HTTP 404 for an invalid/nonexistent user, or 409 for
            an unsupported stored format. Invalid path input receives HTTP 422
            from FastAPI before entry.
        Exception: Other persistence/configuration failures become HTTP 500.
    """
    # 1. Preserve the repository's modern/legacy shape and optional-result contract.
    try:
        record = repository.active_routine_record(user_id)
        if record is None:
            return None
        # 2. Expose persistence identity outside the existing plan body.
        routine_id, routine = record
        response.headers["X-Routine-Id"] = str(routine_id)
        return routine
    # 3. Distinguish absent users from existing but unreadable saved plans.
    except RoutineInputError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RoutineDataError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
