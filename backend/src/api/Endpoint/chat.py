from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status

from api.DataClasses.pipeline.ChatRequest import ChatRequest
from api.DataClasses.pipeline.ChatResponse import ChatResponse
from api.documentation import INTERNAL_SERVER_ERROR_RESPONSE, VALIDATION_ERROR_RESPONSE
from api.redis_deps import get_n_turns, get_set_turn
from systems.pipeline.Pipeline import Pipeline
from utils.routinemaker.func.repository import RoutineInputError


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
                "single URL path segment. Loads recent conversation memory and "
                "stores successful turns in process-local session storage."
            ),
            examples=["session-20261014-morning-workout"],
        ),
    ],
    request: ChatRequest,
    pipeline: Annotated[Pipeline, Depends(get_pipeline)],
) -> ChatResponse:
    """Route a question and execute the selected gym-assistance system.

    **Business rules:** `query` and `language` are both required; only optional
    `user_id` is also accepted. Other fields are rejected. Queries cannot be blank.
    Language must be `ES` or `EN`.
    The query is passed through unchanged, including surrounding whitespace.
    The `id` path parameter is required and identifies the caller's session.
    It is not an authentication credential and is not checked against a session
    store. The latest two stored turns provide conversation context; successful
    turns are retained in process-local session memory, which is lost on restart.

    Exercise explanations return a list of original database fields plus one
    generated llm_explanation per exercise. Missing, ambiguous, or unmatched
    exercise names return a text clarification request. Past-routine analysis
    returns text. Routine Maker
    returns a structured result and may ask for missing requirements rather than
    produce a routine. Unsupported questions return a localized no-match answer
    with HTTP 200, not an error. Every successful response includes `subsystem`,
    the ID selected by the orchestrator (`no_system` for unsupported questions),
    alongside the existing `response` payload. Routing runs once per request.

    Routine requests require `user_id` identifying an existing database user.
    Draft JSON and collected parameters are cached per session and user. New
    routines and edits return `awaiting_confirmation` without database writes.
    An explicit confirmation on a later turn saves a new inactive version;
    the original routine and active selection remain unchanged.

    **Side effects:** routing and selected systems may call Gemini and consume
    provider quota. Successful turns are stored for follow-up explanations.
    This endpoint does not accept explicit history or previous routine state.

    **Permissions:** no authentication or authorization is currently required.
    Provider credentials are supplied by the server, not by callers.

    Invalid requests return HTTP 422 before pipeline execution. Configuration,
    provider, and processing failures propagate as HTTP 500; no successful
    fallback response is generated.
    """
    try:
        result = pipeline.handle_with_subsystem(
            request.query, request.language, session_id=id,
            **({"user_id": request.user_id} if request.user_id is not None else {}),
        )
    except RoutineInputError as error:
        raise HTTPException(status_code=422, detail=[{
            "loc": ["body", "user_id"], "msg": str(error), "type": "value_error",
        }]) from error
    return ChatResponse(subsystem=result.subsystem, response=result.response)
