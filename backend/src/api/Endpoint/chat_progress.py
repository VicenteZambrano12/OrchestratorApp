"""Adapt synchronous workflow notifications to the chat NDJSON transport.

A request-local progress listener bridges worker-thread events into an asyncio
queue. HTTP 200 is established by StreamingResponse; subsequent workflow errors
are terminal records, not new HTTP statuses. SQL progress exposes statement
templates and provider/file metadata, not bound parameters or database rows.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from threading import Event

from fastapi.responses import StreamingResponse

from api.DataClasses.pipeline.ChatResponse import ChatResponse
from obervability.logger import Logger
from utils.pipeline.dataclass.models import PipelineResult
from utils.pipeline.progress import progress_listener, report_progress
from utils.routinemaker.func.repository import RoutineInputError


logger = Logger.get_logger(__name__)


def stream_chat(run: Callable[[], PipelineResult]) -> StreamingResponse:
    """Build a progress stream around one synchronous pipeline execution.

    Args:
        run (Callable[[], PipelineResult]): Zero-argument execution closure from
            the chat endpoint; it owns routing, model/tool work, and persistence.

    Returns:
        StreamingResponse: HTTP 200 application/x-ndjson response with caching
        and proxy buffering disabled. Execution begins when its body is consumed.
        Records include progress, idle heartbeats, and one terminal result or
        error; RoutineInputError uses status 422 and other errors use 500.
    """
    async def events() -> AsyncIterator[str]:
        """Run the workflow off-loop and yield queued NDJSON records.

        Yields:
            str: Serialized, newline-terminated progress or
            heartbeat records followed by one terminal result/error.

        Raises:
            asyncio.CancelledError: If the consuming request task is cancelled;
                finalization still closes delivery and cancels the worker task.
            Exception: Serialization or event-loop failures propagate to the
                response consumer after worker cleanup.
        """
        # 1. Isolate delivery state per stream while workflow code stays synchronous.
        logger.debug("Chat progress stream started")
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        closed = Event()

        def emit(event: dict[str, object]) -> None:
            """Schedule a workflow record onto the stream's owning event loop.

            Args:
                event (dict[str, object]): JSON-compatible progress or terminal
                    record produced by the worker.

            Returns:
                None: Closed streams silently ignore later worker notifications.

            Raises:
                RuntimeError: If the owning loop has closed before scheduling.
            """
            # 2. Bridge threads through the loop rather than mutating its queue directly.
            if not closed.is_set():
                loop.call_soon_threadsafe(queue.put_nowait, event)

        def execute() -> None:
            """Translate synchronous workflow outcomes into terminal records.

            The listener applies only during this execution. Model, database,
            and plan-validation errors are not retried by the transport; the
            underlying systems retain their own validation/retry behavior.

            Returns:
                None: Queues the ChatResponse result or an error record. Domain
                input errors include their message; other errors omit details.
            """
            # 3. Attach real stage notifications and emit exactly one outcome on success.
            try:
                with progress_listener(lambda step: emit({"type": "progress", **step})):
                    result = run()
                    response = ChatResponse(subsystem=result.subsystem, response=result.response)
                    report_progress("response", "Your response is ready")
                    emit({"type": "result", "data": response.model_dump(mode="json")})
                    logger.debug("Chat progress result queued")
            except RoutineInputError as error:
                logger.warning("Chat progress request rejected error_type=RoutineInputError")
                emit({"type": "error", "status": 422, "message": str(error)})
            except Exception as error:
                logger.error("Chat progress stream failed error_type=%s", type(error).__name__)
                emit({"type": "error", "status": 500})

        # 4. Keep the stream responsive while provider and SQL calls block the worker.
        worker = asyncio.create_task(asyncio.to_thread(execute))
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    # 5. Keep idle connections alive without inventing workflow progress.
                    yield json.dumps({"type": "heartbeat"}) + "\n"
                    continue
                yield json.dumps(event, ensure_ascii=False) + "\n"
                if event["type"] in ("result", "error"):
                    break
        finally:
            # 6. Stop delivery on disconnect; task cancellation cannot stop a running thread.
            closed.set()
            worker.cancel()
            logger.debug("Chat progress stream closed")

    # 7. Prevent intermediaries from caching or buffering live workflow events.
    return StreamingResponse(events(), media_type="application/x-ndjson", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })
