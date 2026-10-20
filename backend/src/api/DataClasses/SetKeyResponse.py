"""Define the session-initialization response shared with OpenAPI clients.

The session endpoint populates this model from the process-local store's
initialization result; it is not an authentication token or durable receipt.
"""

from pydantic import BaseModel, ConfigDict, Field


class SetKeyResponse(BaseModel):
    """Report whether session metadata was initialized in the shared store.

    Attributes:
        id (str): Caller-supplied session identifier used as the hash key.
        created (bool): Whether initialization inserted the creation timestamp;
            false indicates an existing timestamp was left unchanged.
    """

    model_config = ConfigDict(json_schema_extra={"example": {"id": "session-1", "created": True}})

    id: str = Field(..., description="Session identifier used as the hash key.")
    created: bool = Field(
        ...,
        description="True if the key was created; False if it already existed (no-op).",
    )
