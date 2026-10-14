from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from api.DataClasses.pipeline.ChatRequest import ChatRequest
from api.DataClasses.pipeline.ChatResponse import ChatResponse
from api.documentation import INTERNAL_SERVER_ERROR_RESPONSE, VALIDATION_ERROR_RESPONSE
from api.redis_deps import get_n_turns, get_set_turn
from systems.pipeline.Pipeline import Pipeline


router = APIRouter()


def get_pipeline() -> Pipeline:
    return Pipeline(turn_setter=get_set_turn(), turn_getter=get_n_turns())


@router.post(
    "/{id}/chat",
    tags=["Chat"],
    summary="Answer a gym question",
    status_code=status.HTTP_200_OK,
    response_model=ChatResponse,
    responses={
        422: VALIDATION_ERROR_RESPONSE,
        status.HTTP_500_INTERNAL_SERVER_ERROR: INTERNAL_SERVER_ERROR_RESPONSE,
    },
)
def chat(
    id: Annotated[
        str,
        Path(
            description=(
                "Caller-supplied session identifier, represented as an opaque "
                "single URL path segment. Does not load or persist conversation state."
            ),
            examples=["session-20261014-morning-workout"],
        ),
    ],
    request: ChatRequest,
    pipeline: Annotated[Pipeline, Depends(get_pipeline)],
) -> ChatResponse:
    """Route a question and execute the selected gym-assistance system.

    **Business rules:** `query` and `language` are both required; additional
    fields are rejected. Queries cannot be blank. Language must be `ES` or `EN`.
    The query is passed through unchanged, including surrounding whitespace.
    The `id` path parameter is required and identifies the caller's session.
    It is not an authentication credential and is not checked against a session
    store. No conversation state is loaded or persisted for this identifier.

    Exercise explanations and past-routine analysis return text. Routine Maker
    returns a structured result and may ask for missing requirements rather than
    produce a routine. Unsupported questions return a localized no-match answer
    with HTTP 200, not an error. Every successful response includes `subsystem`,
    the ID selected by the orchestrator (`no_system` for unsupported questions),
    alongside the existing `response` payload. Routing runs once per request.

    **Side effects:** routing and selected systems may call Gemini and consume
    provider quota. This endpoint does not retain conversation history or accept
    previous routine state.

    **Permissions:** no authentication or authorization is currently required.
    Provider credentials are supplied by the server, not by callers.

    Invalid requests return HTTP 422 before pipeline execution. Configuration,
    provider, and processing failures propagate as HTTP 500; no successful
    fallback response is generated.
    """
    result = pipeline.handle_with_subsystem(
        request.query, request.language, session_id=id
    )
    return ChatResponse(subsystem=result.subsystem, response=result.response)
