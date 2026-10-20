"""Provide process-local Redis-compatible conversation and routine memory.

Layout (see redis_schema.json): one hash per session id, one field per
auto-incremental turn id, each value a JSON string with user_query,
system_response and subsystem_chosen. Routine turns also contain a structured
routine object, separate from the response message.

Metadata and per-user draft state occupy nonnumeric hash fields and are excluded
from turn enumeration. The default fakeredis client is in-memory rather than a
persistent Redis service; state is lost when its backing process ends. Incremental
turn allocation is a read-then-write operation, not a transactional counter.
"""

import json
from typing import Optional

import fakeredis

from obervability.logger import Logger


logger = Logger.get_logger(__name__)


class RedisClient:
    """Store chat turns and routine drafts behind a Redis-compatible interface.

    Attributes:
        client (fakeredis.FakeRedis): Injected or newly created in-memory client.
            Default clients decode stored responses as strings.
    """

    def __init__(self, client: Optional[fakeredis.FakeRedis] = None) -> None:
        """Bind an injected client or create an isolated in-memory store.

        Args:
            client: Optional fakeredis client shared with other consumers.

        Returns:
            None: Initializes the client reference.
        """
        # 1. Permit shared test/application state without requiring external Redis.
        self.client = client or fakeredis.FakeRedis(decode_responses=True)

    @Logger.trace(logger)
    def add_turn(
        self,
        session_id: str,
        user_query: str,
        system_response: str,
        subsystem_chosen: str,
        *,
        routine: dict[str, object] | None = None,
    ) -> int:
        """Append a conversation turn after the highest existing numeric ID.

        Args:
            session_id: Session hash key, created implicitly if absent.
            user_query: Original query or an empty string for a button action.
            system_response: Textual agent response used as later context.
            subsystem_chosen: Selected orchestration subsystem identifier.
            routine: Optional structured payload for routine-maker turns.

        Returns:
            int: Newly allocated turn identifier, starting at one.

        Raises:
            TypeError: Turn data cannot be serialized to JSON.
        """
        # 1. Allocate from numeric turn fields, ignoring metadata and draft state.
        turn_id = self._last_turn_id(session_id) + 1
        # 2. Use the shared serializer so all memory-writing paths agree.
        self.set_turn(
            session_id, turn_id, user_query, system_response, subsystem_chosen,
            routine=routine,
        )
        return turn_id

    @Logger.trace(logger)
    def set_turn(
        self,
        session_id: str,
        turn_id: int,
        user_query: str,
        system_response: str,
        subsystem_chosen: str,
        *,
        routine: dict[str, object] | None = None,
    ) -> None:
        """Write or replace a specific conversation turn.

        Args:
            session_id: Session hash key.
            turn_id: Numeric identifier stored as a hash field string.
            user_query: User text retained for future orchestration.
            system_response: Textual subsystem output.
            subsystem_chosen: Selected subsystem identifier.
            routine: Structured routine included only for ``routine_maker``;
                None is stored explicitly for such turns without a plan.

        Returns:
            None: Writes the serialized turn to the session hash.

        Raises:
            TypeError: The turn payload contains a non-JSON-serializable value.
        """
        # 1. Keep the common conversation envelope independent of agent output shape.
        turn: dict[str, object] = {
            "user_query": user_query,
            "system_response": system_response,
            "subsystem_chosen": subsystem_chosen,
        }
        # 2. Separate routine structure from response text for later agent context.
        if subsystem_chosen == "routine_maker":
            turn["routine"] = routine
        self.client.hset(session_id, str(turn_id), json.dumps(turn))
        logger.debug("Conversation turn stored")

    def _turn_ids(self, session_id: str) -> list[int]:
        """Enumerate numeric turn fields while excluding session metadata.

        Args:
            session_id: Session hash key.

        Returns:
            list[int]: Numeric field IDs in ascending order.
        """
        # 1. Exclude creation timestamps and per-user routine-state fields.
        return sorted(int(k) for k in self.client.hkeys(session_id) if k.isdigit())

    def _last_turn_id(self, session_id: str) -> int:
        """Resolve the latest numeric turn identifier.

        Args:
            session_id: Session hash key.

        Returns:
            int: Highest numeric turn ID, or zero when no turns exist.
        """
        # 1. Reuse metadata-aware enumeration to maintain turn numbering.
        ids = self._turn_ids(session_id)
        return ids[-1] if ids else 0

    @Logger.trace(logger)
    def get_turn(self, session_id: str, turn_id: int) -> Optional[dict]:
        """Read a stored conversation turn without synthesizing missing history.

        Args:
            session_id: Session hash key.
            turn_id: Numeric turn field to retrieve.

        Returns:
            Optional[dict]: Decoded turn payload, or None when absent.

        Raises:
            json.JSONDecodeError: Stored content is not valid JSON.
        """
        # 1. Preserve absent history as None rather than an invented conversation.
        value = self.client.hget(session_id, str(turn_id))
        return json.loads(value) if value is not None else None

    @Logger.trace(logger)
    def get_routine_state(self, session_id: str, user_id: int) -> str | None:
        """Read serialized routine workflow state scoped to session and user.

        Args:
            session_id: Session hash key.
            user_id: Database user identifier qualifying the draft field.

        Returns:
            str | None: Stored JSON text, or None when no state exists.
        """
        # 1. Isolate users' routine drafts while keeping them outside chat turns.
        return self.client.hget(session_id, f"routine_state:{user_id}")

    @Logger.trace(logger)
    def set_routine_state(self, session_id: str, user_id: int, state: str) -> None:
        """Replace serialized routine workflow state without validating its schema.

        Args:
            session_id: Session hash key.
            user_id: Database user identifier qualifying the draft field.
            state: JSON text validated by the routine workflow, not this store.

        Returns:
            None: Writes the user's nonnumeric state field.
        """
        # 1. Leave schema ownership with the workflow's RoutineState model.
        self.client.hset(session_id, f"routine_state:{user_id}", state)
        logger.debug("Routine state stored")

    @Logger.trace(logger)
    def get_session(self, session_id: str) -> dict[int, dict]:
        """Read the full conversation in ascending numeric turn order.

        Args:
            session_id: Session hash key.

        Returns:
            dict[int, dict]: Ordered turn-ID mapping excluding metadata.

        Raises:
            json.JSONDecodeError: A stored turn contains invalid JSON.
        """
        # 1. Reuse numeric enumeration and the common turn decoder.
        return {i: self.get_turn(session_id, i) for i in self._turn_ids(session_id)}

    @Logger.trace(logger)
    def get_last_turn(self, session_id: str) -> Optional[dict]:
        """Read the most recent conversation turn.

        Args:
            session_id: Session hash key.

        Returns:
            Optional[dict]: Last turn payload, or None when no turns exist.

        Raises:
            json.JSONDecodeError: The latest stored turn is invalid JSON.
        """
        # 1. Distinguish missing history from a session containing only metadata.
        last = self._last_turn_id(session_id)
        return self.get_turn(session_id, last) if last else None

    @Logger.trace(logger)
    def delete_turn(self, session_id: str, turn_id: int) -> bool:
        """Remove one turn without renumbering the remaining conversation.

        Args:
            session_id: Session hash key.
            turn_id: Turn field to remove.

        Returns:
            bool: Whether a matching field was removed.
        """
        # 1. Preserve stable IDs for all unaffected conversation turns.
        return bool(self.client.hdel(session_id, str(turn_id)))

    @Logger.trace(logger)
    def delete_session(self, session_id: str) -> bool:
        """Remove a session's conversation, metadata, and cached routine state.

        Args:
            session_id: Session hash key.

        Returns:
            bool: Whether the session hash existed and was removed.
        """
        # 1. Delete the shared hash so no draft state survives session removal.
        deleted = bool(self.client.delete(session_id))
        logger.info("Conversation session deletion completed existed=%s", deleted)
        return deleted

    @Logger.trace(logger)
    def session_exists(self, session_id: str) -> bool:
        """Check for any state under the session key.

        Args:
            session_id: Session hash key.

        Returns:
            bool: True for a key containing turns, metadata, or routine state.
        """
        # 1. Test key existence rather than requiring a completed chat turn.
        return bool(self.client.exists(session_id))

    @Logger.trace(logger)
    def turn_count(self, session_id: str) -> int:
        """Count conversation turns while excluding nonnumeric state fields.

        Args:
            session_id: Session hash key.

        Returns:
            int: Number of numeric turn fields.
        """
        # 1. Use the same field filter as history retrieval.
        return len(self._turn_ids(session_id))

    @Logger.trace(logger)
    def list_sessions(self) -> list[str]:
        """List all store keys under the session-only namespace convention.

        Returns:
            list[str]: All keys sorted lexicographically.
        """
        # 1. Enumerate the in-memory namespace without inspecting conversation data.
        return sorted(self.client.keys("*"))

    @Logger.trace(logger)
    def flush(self) -> None:
        """Clear every database in the backing Redis-compatible server.

        Returns:
            None: Removes all sessions, turns, metadata, and draft state
                reachable through the backing server.
        """
        # 1. Reset the complete backing store, not just the selected session.
        self.client.flushall()
        logger.info("Conversation store cleared")
