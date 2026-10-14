from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from api.DataClasses.SetKeyResponse import SetKeyResponse
from api.documentation import INTERNAL_SERVER_ERROR_RESPONSE, VALIDATION_ERROR_RESPONSE
from api.redis_deps import SetKey, get_set_key


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
) -> SetKeyResponse:
    """Create the session hash for `id` in the in-memory (fakeredis) store.

    Initializes the hash with a `created_at` timestamp. Idempotent: if the key
    already exists nothing is changed and `created` is `false`.

    **Side effects:** writes to process-local memory; data is lost on restart.
    **Permissions:** no authentication or authorization is required.
    """
    return SetKeyResponse(id=id, created=key_setter.set(id))
