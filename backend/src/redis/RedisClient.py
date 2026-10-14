"""Demo Redis client backed by fakeredis, storing conversation state.

Layout (see redis_schema.json): one hash per session id, one field per
auto-incremental turn id, each value a JSON string with user_query,
system_response and subsystem_chosen.
"""

import json
from typing import Optional

import fakeredis


class RedisClient:
    def __init__(self, client: Optional[fakeredis.FakeRedis] = None) -> None:
        self.client = client or fakeredis.FakeRedis(decode_responses=True)

    def add_turn(
        self,
        session_id: str,
        user_query: str,
        system_response: str,
        subsystem_chosen: str,
    ) -> int:
        """Append a turn to the session and return its turn id."""
        turn_id = self._last_turn_id(session_id) + 1
        self.set_turn(session_id, turn_id, user_query, system_response, subsystem_chosen)
        return turn_id

    def set_turn(
        self,
        session_id: str,
        turn_id: int,
        user_query: str,
        system_response: str,
        subsystem_chosen: str,
    ) -> None:
        turn = {
            "user_query": user_query,
            "system_response": system_response,
            "subsystem_chosen": subsystem_chosen,
        }
        self.client.hset(session_id, str(turn_id), json.dumps(turn))

    def _turn_ids(self, session_id: str) -> list[int]:
        """Turn ids only; metadata fields such as created_at are ignored."""
        return sorted(int(k) for k in self.client.hkeys(session_id) if k.isdigit())

    def _last_turn_id(self, session_id: str) -> int:
        ids = self._turn_ids(session_id)
        return ids[-1] if ids else 0

    def get_turn(self, session_id: str, turn_id: int) -> Optional[dict]:
        value = self.client.hget(session_id, str(turn_id))
        return json.loads(value) if value is not None else None

    def get_routine_state(self, session_id: str, user_id: int) -> str | None:
        return self.client.hget(session_id, f"routine_state:{user_id}")

    def set_routine_state(self, session_id: str, user_id: int, state: str) -> None:
        self.client.hset(session_id, f"routine_state:{user_id}", state)

    def get_session(self, session_id: str) -> dict[int, dict]:
        """Return all turns of a session ordered by turn id."""
        return {i: self.get_turn(session_id, i) for i in self._turn_ids(session_id)}

    def get_last_turn(self, session_id: str) -> Optional[dict]:
        last = self._last_turn_id(session_id)
        return self.get_turn(session_id, last) if last else None

    def delete_turn(self, session_id: str, turn_id: int) -> bool:
        return bool(self.client.hdel(session_id, str(turn_id)))

    def delete_session(self, session_id: str) -> bool:
        return bool(self.client.delete(session_id))

    def session_exists(self, session_id: str) -> bool:
        return bool(self.client.exists(session_id))

    def turn_count(self, session_id: str) -> int:
        return len(self._turn_ids(session_id))

    def list_sessions(self) -> list[str]:
        return sorted(self.client.keys("*"))

    def flush(self) -> None:
        self.client.flushall()
