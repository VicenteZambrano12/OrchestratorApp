"""Initialize or reset caller-named sessions in process-local storage.

The router shares its store with chat memory and routine drafts. Session names
are scopes rather than credentials, and initialization makes no provider calls.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from api.DataClasses.SetKeyResponse import SetKeyResponse
from api.documentation import INTERNAL_SERVER_ERROR_RESPONSE, VALIDATION_ERROR_RESPONSE
from api.redis_deps import RedisClient, SetKey, get_routine_store, get_set_key


router = APIRouter()


@router.post(
    "/{id}/key",
    tags=["Session"],
    summary="Create the in-memory session hash key",
    status_code=status.HTTP_200_OK,
    response_model=SetKeyResponse,
    responses={
        422: VALIDATION_ERROR_RESPONSE,
        status.HTTP_500_INTERNAL_SERVER_ERROR: INTERNAL_SERVER_ERROR_RESPONSE,
    },
)
def set_key(
    id: Annotated[
        str,
        Path(
            description="Session identifier used as the in-memory hash key.",
            examples=["session-20261014-morning-workout"],
        ),
    ],
    key_setter: Annotated[SetKey, Depends(get_set_key)],
    store: Annotated[RedisClient, Depends(get_routine_store)],
    reset: Annotated[bool, Query(description="Clear this session's conversation and routine draft before initialization.")] = False,
) -> SetKeyResponse:
    """Create the session hash for `id` in the in-memory (fakeredis) store.

    Initializes the hash with a `created_at` timestamp. Idempotent: if that
    timestamp already exists nothing is changed and `created` is `false`.
    An existing hash without that metadata receives the timestamp.
    With `reset=true`, deletes only this session before recreating it.

    **Side effects:** writes to process-local memory; data is lost on restart.
    **Permissions:** no authentication or authorization is required.

    No JSON body is required. The optional boolean ``reset`` query flag defaults
    to false; resetting removes conversation turns and all user draft fields in
    the selected session, not other sessions.

    Args:
        id (str): Opaque session identifier from the URL path.
        key_setter (SetKey): Injected session-metadata initialization adapter.
        store (RedisClient): Shared client used to delete a session on reset.
        reset (bool): Whether to clear the session before initialization.

    Returns:
        SetKeyResponse: HTTP 200 with the session ID and timestamp-insertion
        result in ``created``.

    Raises:
        Exception: Unhandled store/processing failures become HTTP 500.
            FastAPI rejects invalid query input with HTTP 422 before entry.
    """
    # 1. Reset only the caller-selected session, including memory and cached drafts.
    if reset:
        store.delete_session(id)
    # 2. Initialize metadata idempotently through the same shared-store adapter.
    return SetKeyResponse(id=id, created=key_setter.set(id))
