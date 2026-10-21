"""Adapt session memory into the bounded history consumed by agent routing.

The client is injected because the local redis directory shares its name with
the installed Redis package. Numeric turn ordering excludes session metadata
and per-user routine state from the conversational context.
"""

from typing import Any

from obervability.logger import Logger


logger = Logger.get_logger(__name__)


class GetNTurns:
    """Retrieve bounded conversation history through an injected store.

    Attributes:
        redis_client (Any): Store providing ``_turn_ids`` and ``get_turn``.
    """

    def __init__(self, redis_client: Any) -> None:
        """Bind the shared session-memory client.

        Args:
            redis_client: Store with numeric turn enumeration and retrieval.

        Returns:
            None: Retains the injected store.
        """
        # 1. Reuse shared memory rather than creating isolated agent context.
        self.redis_client = redis_client

    @Logger.trace(logger)
    def get(self, session_id: str, n: int) -> dict[int, dict]:
        """Read the latest turns in chronological order.

        Args:
            session_id: Caller-supplied session hash key.
            n: Maximum turns to include; nonpositive values request no history.

        Returns:
            dict[int, dict]: Turn-ID mapping ordered oldest first within the
                selected window; empty when no history is requested or stored.

        Raises:
            ValueError: A stored turn contains invalid JSON.
        """
        # 1. Treat a nonpositive window as an explicit request for no context.
        if n <= 0:
            return {}
        # 2. Select numeric turns only so metadata never enters agent memory.
        ids = self.redis_client._turn_ids(session_id)[-n:]
        return {i: self.redis_client.get_turn(session_id, i) for i in ids}
