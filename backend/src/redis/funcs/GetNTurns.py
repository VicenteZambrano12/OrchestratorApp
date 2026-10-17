"""Retrieve the last N turns of a session."""

from typing import Any


class GetNTurns:
    # The local `redis` folder is shadowed by the installed redis package,
    # so the client is injected instead of imported.
    def __init__(self, redis_client: Any) -> None:
        self.redis_client = redis_client

    def get(self, session_id: str, n: int) -> dict[int, dict]:
        """Return the last n turns (oldest first), keyed by turn id."""
        if n <= 0:
            return {}
        ids = self.redis_client._turn_ids(session_id)[-n:]
        return {i: self.redis_client.get_turn(session_id, i) for i in ids}
