"""Initialize session metadata without overwriting existing conversation state.

The injected memory client avoids the local redis directory's import collision
with the installed package. Session creation records a UTC timestamp; it is not
an authentication or authorization operation.
"""

from datetime import datetime, timezone
from typing import Any

from obervability.logger import Logger


logger = Logger.get_logger(__name__)


class SetKey:
    """Create session hashes idempotently through an injected memory client.

    Attributes:
        redis_client (Any): Store exposing the Redis-compatible ``client``.
    """

    def __init__(self, redis_client: Any) -> None:
        """Bind the store used by session initialization.

        Args:
            redis_client: Shared store exposing a client with ``hsetnx``.

        Returns:
            None: Retains the injected store.
        """
        # 1. Share the same memory namespace as chat and routine workflows.
        self.redis_client = redis_client

    @Logger.trace(logger)
    def set(self, session_id: str) -> bool:
        """Set creation metadata only when the hash field is absent.

        Args:
            session_id: Session hash key to initialize.

        Returns:
            bool: True when ``created_at`` was inserted, otherwise False.
                An existing hash lacking this field also returns True.
        """
        # 1. Use field-level conditional insertion to preserve existing turns.
        created = bool(
            self.redis_client.client.hsetnx(
                session_id, "created_at", datetime.now(timezone.utc).isoformat()
            )
        )
        logger.info("Conversation session initialized created=%s", created)
        return created
