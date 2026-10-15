"""Stream real workflow notifications without changing the JSON chat contract."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from threading import Event

from fastapi.responses import StreamingResponse

from api.DataClasses.pipeline.ChatResponse import ChatResponse
from utils.pipeline.dataclass.models import PipelineResult
from utils.pipeline.progress import progress_listener, report_progress
from utils.routinemaker.func.repository import RoutineInputError


logger = logging.getLogger(__name__)


def stream_chat(run: Callable[[], PipelineResult]) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        closed = Event()

        def emit(event: dict[str, object]) -> None:
            if not closed.is_set():
                loop.call_soon_threadsafe(queue.put_nowait, event)

        def execute() -> None:
            try:
                with progress_listener(lambda step: emit({"type": "progress", **step})):
                    result = run()
                    response = ChatResponse(subsystem=result.subsystem, response=result.response)
                    report_progress("response", "Your response is ready")
                    emit({"type": "result", "data": response.model_dump(mode="json")})
            except RoutineInputError as error:
                emit({"type": "error", "status": 422, "message": str(error)})
            except Exception:
                logger.exception("Chat progress stream failed")
                emit({"type": "error", "status": 500})

        worker = asyncio.create_task(asyncio.to_thread(execute))
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield json.dumps({"type": "heartbeat"}) + "\n"
                    continue
                yield json.dumps(event, ensure_ascii=False) + "\n"
                if event["type"] in ("result", "error"):
                    break
        finally:
            closed.set()
            worker.cancel()

    return StreamingResponse(events(), media_type="application/x-ndjson", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })
