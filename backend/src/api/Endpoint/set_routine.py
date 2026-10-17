from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path as ApiPath, Query, Response
from pydantic import ValidationError

from api.Endpoint.active_routine import get_routine_repository
from api.redis_deps import SetTurn, get_routine_store, get_set_turn
from utils.routinemaker.dataclass.models import RoutinePlan
from utils.routinemaker.func.handle import RoutineStore, save_draft
from utils.routinemaker.func.repository import RoutineInputError, RoutineRepository


router = APIRouter()


@router.put(
    "/users/{user_id}/routine",
    response_model=RoutinePlan,
    tags=["Users"],
    responses={
        200: {"headers": {"X-Routine-Id": {
            "description": "Database ID of the saved routine version.",
            "schema": {"type": "integer"},
        }}},
        404: {"description": "The user does not exist."},
        422: {"description": "The routine or user ID is invalid."},
    },
)
def set_active_routine(
    user_id: Annotated[int, ApiPath(gt=0)],
    response: Response,
    routine: RoutinePlan,
    repository: Annotated[RoutineRepository, Depends(get_routine_repository)],
    state_store: Annotated[RoutineStore, Depends(get_routine_store)],
    turn_setter: Annotated[SetTurn, Depends(get_set_turn)],
    session_id: Annotated[str | None, Query(min_length=1)] = None,
    draft_id: Annotated[str | None, Query(min_length=1)] = None,
    language: Literal["EN", "ES"] = "EN",
):
    """Save a new active version, preserving previous versions as inactive.

    Optional session_id and draft_id must be supplied together. They confirm the
    exact cached preview idempotently, preserve its parameters, and update chat
    state and memory. Stale, mismatched, or unavailable previews return 422.
    Without those query parameters, save the supplied routine as a new version.
    """
    try:
        repository.validate_user(user_id)
    except RoutineInputError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    if (session_id is None) != (draft_id is None):
        raise HTTPException(status_code=422, detail="session_id and draft_id must be supplied together.")
    try:
        if session_id is not None and draft_id is not None:
            result = save_draft(
                repository=repository, state_store=state_store,
                session_id=session_id, user_id=user_id, draft_id=draft_id,
                language=language, routine=routine,
            )
            if result.status != "saved":
                raise RoutineInputError(result.message)
            routine_id = result.routine_id
            turn_setter.set(
                session_id, "", result.message, "routine_maker",
                routine=routine.model_dump(mode="json"),
            )
        else:
            routine_id = repository.set_active_routine(user_id, routine)
    except RoutineInputError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if routine_id is None:
        raise RuntimeError("The saved routine has no database ID.")
    response.headers["X-Routine-Id"] = str(routine_id)
    return routine
