"""Publish request-local workflow and SQL-template events without transport coupling.

Context variables isolate the active listener and stage across request contexts.
Consumers attach a synchronous callback for the duration of a workflow. SQL
events expose only query templates and a database label, never bound parameters
or result rows; this module reports execution but does not execute queries.

Attributes:
    _listener (ContextVar[Callable[[dict[str, str]], None] | None]): Active
        request's optional synchronous event consumer.
    _current_node (ContextVar[str]): Current stage ID used to parent SQL events;
        defaults to ``request``.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from uuid import uuid4

from obervability.logger import Logger


logger = Logger.get_logger(__name__)
_listener: ContextVar[Callable[[dict[str, str]], None] | None] = ContextVar(
    "pipeline_progress_listener", default=None,
)
_current_node: ContextVar[str] = ContextVar("pipeline_current_node", default="request")


@contextmanager
def progress_listener(callback: Callable[[dict[str, str]], None]) -> Iterator[None]:
    """Temporarily install a progress callback and reset the stage to request.

    Nested contexts restore the previous listener and stage even when workflow
    execution raises.

    Args:
        callback (Callable[[dict[str, str]], None]): Synchronous event consumer.

    Yields:
        None: Control to the workflow with this request's listener active.

    Raises:
        Exception: Exceptions from the managed block propagate after cleanup.
    """
    # 1. Save context tokens so nested/request-local instrumentation is reversible.
    token = _listener.set(callback)
    node_token = _current_node.set("request")
    try:
        yield
    finally:
        # 2. Restore both contexts on success or failure to avoid cross-request state.
        _listener.reset(token)
        _current_node.reset(node_token)


def report_progress(node: str, label: str) -> None:
    """Advance the current stage and notify an installed event consumer.

    Args:
        node (str): Stable stage ID also used as the parent of subsequent SQL events.
        label (str): Human-readable workflow activity.

    Returns:
        None: The context is updated even when no listener is installed.

    Raises:
        Exception: Listener failures propagate to the workflow caller.
    """
    # 1. Update parentage before callback delivery so later SQL events attach here.
    _current_node.set(node)
    logger.debug("Workflow stage advanced stage=%s", node)
    listener = _listener.get()
    if listener is not None:
        listener({"id": node, "label": label})


def report_sql(query: str, database: str, *, database_type: str = "sqlite") -> None:
    """Publish a SQL-template event under the current workflow stage.

    Args:
        query (str): Query template only; callers must not insert bound values.
        database (str): Database path/name, reduced to its basename for display.
        database_type (str): ``postgresql`` for PostgreSQL labeling, otherwise SQLite.

    Returns:
        None: No event is emitted when no listener is active.

    Raises:
        Exception: Listener failures propagate to the SQL execution caller.
    """
    # 1. Omit work when unobserved; otherwise emit a unique child without row data.
    listener = _listener.get()
    if listener is not None:
        listener({
            "id": f"sql_{uuid4().hex}",
            "label": "Executing SQL query",
            "kind": "sql",
            "parent": _current_node.get(),
            "sql": query,
            "source": f"{'PostgreSQL' if database_type == 'postgresql' else 'SQLite'} / {Path(database).name}",
        })
