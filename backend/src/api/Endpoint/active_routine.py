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
    """Return the user's active saved routine, or null when they have none."""
    try:
        record = repository.active_routine_record(user_id)
        if record is None:
            return None
        routine_id, routine = record
        response.headers["X-Routine-Id"] = str(routine_id)
        return routine
    except RoutineInputError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RoutineDataError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
