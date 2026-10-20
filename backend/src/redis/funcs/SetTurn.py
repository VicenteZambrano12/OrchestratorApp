"""Adapt successful agent outputs into incremental conversation-memory turns.

The injected store avoids the local redis package-name collision and shares
state with history readers. Routine results retain structured plan data
separately from the textual response so later agent turns can recover context.
"""

from typing import Any


class SetTurn:
    """Append conversation turns through the shared memory store.

    Attributes:
        redis_client (Any): Injected store implementing ``add_turn``.
    """

    def __init__(self, redis_client: Any) -> None:
        """Bind the conversation store used by the pipeline.

        Args:
            redis_client: Shared store with incremental turn insertion.

        Returns:
            None: Retains the injected store.
        """
        # 1. Keep turn persistence independent of concrete store imports.
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
        """Append an agent response and optional structured routine.

        Args:
            session_id: Session hash key; an existing hash is not required.
            user_query: Original user text, or an empty string for button actions.
            system_response: Textual agent response stored for later context.
            subsystem_chosen: Identifier of the agent selected by orchestration.
            routine: Optional JSON-serializable routine payload forwarded to
                the store for routine-maker turns.

        Returns:
            int: Newly assigned incremental turn identifier.

        Raises:
            TypeError: A supplied routine cannot be serialized by the store.
        """
        # 1. Preserve agent identity and structured output at the memory boundary.
        return self.redis_client.add_turn(
            session_id, user_query, system_response, subsystem_chosen, routine=routine,
        )
