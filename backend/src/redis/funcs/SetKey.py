"""Set a new turn entry in the session hash."""

from datetime import datetime, timezone
from typing import Any


class SetKey:
    # The local `redis` folder is shadowed by the installed redis package,
    # so the client is injected instead of imported.
    def __init__(self, redis_client: Any) -> None:
        self.redis_client = redis_client

    def set(self, session_id: str) -> bool:
        """Create the session hash with a created_at field; no-op if it exists.

        Returns True if the key was created.
        """
        return bool(
            self.redis_client.client.hsetnx(
                session_id, "created_at", datetime.now(timezone.utc).isoformat()
            )
        )
