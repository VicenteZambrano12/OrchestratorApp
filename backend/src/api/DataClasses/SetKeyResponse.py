from pydantic import BaseModel, ConfigDict, Field


class SetKeyResponse(BaseModel):
    """Result of creating the in-memory session hash key."""

    model_config = ConfigDict(json_schema_extra={"example": {"id": "session-1", "created": True}})

    id: str = Field(..., description="Session identifier used as the hash key.")
    created: bool = Field(
        ...,
        description="True if the key was created; False if it already existed (no-op).",
    )
