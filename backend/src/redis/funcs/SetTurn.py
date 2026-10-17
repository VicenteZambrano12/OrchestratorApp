"""Add a new incremental turn to an existing session hash."""

from typing import Any


class SetTurn:
    # The local `redis` folder is shadowed by the installed redis package,
    # so the client is injected instead of imported.
    def __init__(self, redis_client: Any) -> None:
        self.redis_client = redis_client

    def set(
        self,
        session_id: str,
        user_query: str,
        system_response: str,
        subsystem_chosen: str,
        *,
        routine: dict[str, object] | None = None,
    ) -> int:
        """Store the next turn for the session and return its turn id."""
        return self.redis_client.add_turn(
            session_id, user_query, system_response, subsystem_chosen, routine=routine,
        )
