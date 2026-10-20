"""Expose chat execution and deterministic confirmation of routine previews.

The chat route delegates agent selection, prompt loading, database/catalog
helpers, and Gemini calls to Pipeline and its systems. JSON and NDJSON clients
share one request model and result envelope. Direct draft confirmation uses
server-cached state without invoking the orchestrator or a model.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from fastapi.responses import StreamingResponse

from api.DataClasses.pipeline.ChatRequest import ChatRequest
from api.DataClasses.pipeline.ChatResponse import ChatResponse
from api.DataClasses.pipeline.SaveRoutineRequest import SaveRoutineRequest
from api.Endpoint.chat_progress import stream_chat
from api.documentation import INTERNAL_SERVER_ERROR_RESPONSE, VALIDATION_ERROR_RESPONSE
from api.redis_deps import SetTurn, get_n_turns, get_routine_store, get_set_turn
from systems.pipeline.Pipeline import Pipeline
from utils.routinemaker.func.repository import RoutineInputError
from utils.routinemaker.func.repository import RoutineRepository
from utils.routinemaker.func.handle import RoutineStore, save_draft


router = APIRouter()


def get_pipeline() -> Pipeline:
    """Construct a request pipeline wired to shared conversation memory.

    Systems and their model clients are initialized lazily by the pipeline.
    Its default history window is two turns; adapter instances share one
    process-local session store with the routine-save endpoints.

    Returns:
        Pipeline: Pipeline configured with turn-writing and history adapters.
    """
    # 1. Connect lazy workflow execution to the shared session-memory adapters.
    return Pipeline(turn_setter=get_set_turn(), turn_getter=get_n_turns())


def get_routine_repository() -> RoutineRepository:
    """Create the direct-confirmation persistence dependency.

    Returns:
        RoutineRepository: Repository using runtime-selected database settings.
    """
    # 1. Provide persistence independently of routing and model initialization.
    return RoutineRepository()


@router.post(
    "/{id}/routine/save",
    tags=["Chat"],
    summary="Save a routine preview directly",
    response_model=ChatResponse,
    responses={
        422: VALIDATION_ERROR_RESPONSE,
        500: INTERNAL_SERVER_ERROR_RESPONSE,
    },
)
def save_routine(
    id: str,
    request: SaveRoutineRequest,
    repository: Annotated[RoutineRepository, Depends(get_routine_repository)],
    state_store: Annotated[RoutineStore, Depends(get_routine_store)],
    turn_setter: Annotated[SetTurn, Depends(get_set_turn)],
) -> ChatResponse:
    """Save the specified cached draft as the user's new current routine.

    **Side effects:** atomically inserts an active version and deactivates the
    user's previous routines, preserving their contents. No routing or LLM calls
    occur. Retrying the same draft does not create another version or reactivate
    an older routine. Stale draft identifiers and invalid users return 422.
    Successful saves append a memory turn with an empty user_query (button
    action), a text confirmation, and the structured routine in its own field.

    **Permissions:** caller-supplied session/user scope, not authentication.
    Only the server-cached preview is saved; clients cannot submit plan contents.

    The JSON body requires positive ``user_id``, nonblank ``draft_id``, and
    ``language`` of EN or ES; extra fields are rejected. If no confirmable draft
    exists, the helper may return ``needs_routine`` successfully without a write.

    Args:
        id (str): Session path identifier used to locate the cached preview.
        request (SaveRoutineRequest): Validated JSON confirmation identifiers.
        repository (RoutineRepository): Injected user/plan validation and storage.
        state_store (RoutineStore): Shared cache scoped by session and user.
        turn_setter (SetTurn): Adapter storing successful confirmation memory.

    Returns:
        ChatResponse: HTTP 200 ``routine_maker`` envelope containing the
        confirmation result, including ``saved`` or ``needs_routine``.

    Raises:
        HTTPException: With HTTP 422 and a body-located detail for rejected user
            or draft input. Invalid request bodies also receive 422 from FastAPI.
        Exception: Unhandled cache, database, or validation failures become
            HTTP 500; no model fallback is attempted.
    """
    # 1. Confirm the cached plan instead of trusting client-submitted plan contents.
    try:
        result = save_draft(
            repository=repository, state_store=state_store, session_id=id,
            user_id=request.user_id, draft_id=request.draft_id, language=request.language,
        )
    # 2. Preserve validation-style errors while leaving infrastructure failures visible.
    except RoutineInputError as error:
        raise HTTPException(status_code=422, detail=[{
            "loc": ["body"], "msg": str(error), "type": "value_error",
        }]) from error
    # 3. Store only successful confirmations as button-action conversation turns.
    if result.status == "saved":
        turn_setter.set(
            id, "", result.message, "routine_maker",
            routine=result.routine.model_dump(mode="json") if result.routine else None,
        )
    return ChatResponse(subsystem="routine_maker", response=result)


@router.post(
    "/{id}/chat",
    tags=["Chat"],
    summary="Answer a gym question",
    status_code=status.HTTP_200_OK,
    response_model=ChatResponse,
    responses={
        200: {"content": {"application/x-ndjson": {
            "schema": {"type": "string"},
        }}, "description": "JSON answer, or live progress and a terminal result/error with Accept: application/x-ndjson."},
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
    http_request: Request,
) -> ChatResponse | StreamingResponse:
    """Route a question and execute the selected gym-assistance system.

    Set `Accept: application/x-ndjson` to receive live `progress` events
    (`id`, `label`), optional SQL progress metadata (`kind: sql`, `parent`,
    `sql`: parameterized statement template, `source`: provider and file name),
    optional `heartbeat` events, and a terminal `result`
    (`data`: the ChatResponse envelope) or `error` (`status`, optional `message`).
    Stream processing errors are in-band after HTTP 200; request validation
    still uses HTTP 422. The default JSON response is unchanged.

    **Business rules:** `query` and `language` are both required; optional
    `user_id` and `client_saves_routine` are also accepted. Other fields are rejected. Queries cannot be blank.
    Language must be `ES` or `EN`.
    The query is passed through unchanged, including surrounding whitespace.
    The `id` path parameter is required and identifies the caller's session.
    It is not an authentication credential and is not checked against a session
    store. The latest two stored turns provide conversation context; successful
    turns are retained in process-local session memory, which is lost on restart.

    Exercise explanations return a list of original database fields plus one
    generated llm_explanation per exercise. Missing, ambiguous, or unmatched
    exercise names return a text clarification request. Past-routine analysis
    requires `user_id` and returns `route` (past_day_exercise,
    compare_last_two_workouts or weekly_performance), `day_type`, the user's
    logged workout rows in `data`, and a generated `llm_explain`. Routine Maker
    returns a structured result and may ask for missing requirements rather than
    produce a routine. Unsupported questions return a localized no-match answer
    with HTTP 200, not an error. Every successful response includes `subsystem`,
    the ID selected by the orchestrator (`no_system` for unsupported questions),
    alongside the existing `response` payload. Routing runs once per request.

    Routine requests require `user_id` identifying an existing database user.
    Draft JSON and collected parameters are cached per session and user. New
    routines and edits return `awaiting_confirmation` without database writes.
    An explicit confirmation on a later turn saves a new active version;
    previous versions are preserved but deactivated. The direct routine/save
    endpoint confirms a preview without routing or LLM calls.
    With `client_saves_routine: true`, confirmation instead returns
    `save_requested` with the routine and draft ID without writing to the database.
    The client completes the save through `PUT /users/{user_id}/routine`.

    **Side effects:** routing and selected systems may call Gemini and consume
    provider quota. Successful turns are stored for follow-up explanations.
    This endpoint does not accept explicit history or previous routine state.

    **Permissions:** no authentication or authorization is currently required.
    Provider credentials are supplied by the server, not by callers.

    Invalid requests return HTTP 422 before pipeline execution. Configuration,
    provider, and processing failures propagate as HTTP 500; no successful
    fallback response is generated.

    The orchestrator uses server-managed YAML prompts to select one subsystem;
    it does not execute that subsystem itself. Selected systems load their own
    stage prompts. Exercise extraction and explanations are grounded in catalog
    lookups; history analysis selects a parameterized SQL template and generates
    a separate explanation of retrieved rows. Routine generation validates
    catalog-backed plans before caching previews. These database helpers are
    application-controlled operations, not caller-defined tools or prompts.

    Args:
        id (str): Opaque session path segment for recent turns and draft state.
        request (ChatRequest): JSON body containing required query/language and
            optional positive user_id and client_saves_routine boolean.
        pipeline (Pipeline): Injected routing/execution and conversation dependency.
        http_request (Request): HTTP request whose Accept header selects NDJSON.

    Returns:
        ChatResponse | StreamingResponse: HTTP 200 JSON envelope by default or
        HTTP 200 NDJSON progress stream ending with a result or in-band error.

    Raises:
        HTTPException: With HTTP 422 for RoutineInputError on the JSON path,
            including missing required user context. FastAPI rejects invalid
            request fields with 422 before invocation for either transport.
        Exception: Other JSON-path configuration, provider, validation, or
            processing failures become HTTP 500. The stream reports execution
            failures in-band with status 422 or 500 after HTTP 200 has begun.
    """
    # 1. Share one execution closure so transport choice cannot reroute the request.
    def run():
        """Execute the selected workflow using only explicitly supplied context.

        Returns:
            PipelineResult: Selected subsystem and unchanged workflow payload.

        Raises:
            RoutineInputError: If the selected workflow lacks valid user context.
            Exception: Routing, prompt/configuration, provider, database, and
                processing failures propagate to the chosen transport adapter.
        """
        # 1. Forward explicit caller context through the same pipeline for either transport.
        return pipeline.handle_with_subsystem(
            request.query, request.language, session_id=id,
            **({"user_id": request.user_id} if request.user_id is not None else {}),
            **({"client_saves_routine": True} if request.client_saves_routine else {}),
        )
    # 2. Streaming owns in-band failures; ordinary JSON retains HTTP error mapping.
    if "application/x-ndjson" in http_request.headers.get("accept", ""):
        return stream_chat(run)
    try:
        result = run()
    except RoutineInputError as error:
        raise HTTPException(status_code=422, detail=[{
            "loc": ["body", "user_id"], "msg": str(error), "type": "value_error",
        }]) from error
    # 3. Wrap the workflow result without rewriting its subsystem-specific payload.
    return ChatResponse(subsystem=result.subsystem, response=result.response)
