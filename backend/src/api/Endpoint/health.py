"""Expose public application liveness independently of chat dependencies.

This router returns a fixed validated payload; it does not instantiate agents,
load system prompts, call Gemini, or probe persistence.
"""

from fastapi import APIRouter, status

from api.DataClasses.HealthResponse import HealthResponse
from api.documentation import INTERNAL_SERVER_ERROR_RESPONSE


router = APIRouter()


@router.get(
    "/health",
    tags=["Health"],
    summary="Check application liveness",
    status_code=status.HTTP_200_OK,
    response_model=HealthResponse,
    responses={status.HTTP_500_INTERNAL_SERVER_ERROR: INTERNAL_SERVER_ERROR_RESPONSE},
)
async def health_check() -> dict[str, str]:
    """Check whether the application can respond to an HTTP request.

    Returns `{"status": "ok"}` without contacting Gemini, checking configuration,
    or testing other dependencies. This is a **liveness** check, not a readiness
    guarantee for chat processing.

    **Side effects:** none; no pipeline execution or external API usage.
    **Permissions:** public; no authentication or authorization is required.

    No request body or query parameters are accepted by this handler.

    Returns:
        dict[str, str]: HTTP 200 with ``{"status": "ok"}``, validated against
        HealthResponse. Unhandled server failures use HTTP 500.
    """
    # 1. Report process responsiveness without coupling liveness to providers.
    return {"status": "ok"}
