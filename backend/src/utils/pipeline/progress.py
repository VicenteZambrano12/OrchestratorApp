"""Request-local progress notifications, independent of the transport."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from uuid import uuid4


_listener: ContextVar[Callable[[dict[str, str]], None] | None] = ContextVar(
    "pipeline_progress_listener", default=None,
)
_current_node: ContextVar[str] = ContextVar("pipeline_current_node", default="request")


@contextmanager
def progress_listener(callback: Callable[[dict[str, str]], None]) -> Iterator[None]:
    token = _listener.set(callback)
    node_token = _current_node.set("request")
    try:
        yield
    finally:
        _listener.reset(token)
        _current_node.reset(node_token)


def report_progress(node: str, label: str) -> None:
    _current_node.set(node)
    listener = _listener.get()
    if listener is not None:
        listener({"id": node, "label": label})


def report_sql(query: str, database: str) -> None:
    """Publish query templates only, never bound values or result rows."""
    listener = _listener.get()
    if listener is not None:
        listener({
            "id": f"sql_{uuid4().hex}",
            "label": "Executing SQL query",
            "kind": "sql",
            "parent": _current_node.get(),
            "sql": query,
            "source": f"SQLite / {Path(database).name}",
        })
