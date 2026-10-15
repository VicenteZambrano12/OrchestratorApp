from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    """A gym-assistance question with response language and optional routine owner."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        json_schema_extra={
            "example": {
                "query": "Explain how to perform a barbell squat safely.",
                "language": "EN",
                "client_saves_routine": False,
            }
        },
    )

    query: str = Field(
        ...,
        min_length=1,
        description=(
            "Gym-related question to route to the appropriate system. Must "
            "contain non-whitespace text; original whitespace is preserved."
        ),
        examples=["Explain how to perform a barbell squat safely."],
    )
    language: Literal["ES", "EN"] = Field(
        ...,
        description="Response language: ES for Spanish or EN for English (case-sensitive).",
        examples=["EN", "ES"],
    )
    user_id: int | None = Field(
        default=None, gt=0,
        description="Existing database user ID. Required when routed to Routine Maker; not authentication.",
        examples=[None, 1],
    )
    client_saves_routine: bool = Field(
        default=False,
        description="Return save_requested on confirmation so the client can persist the draft through PUT /users/{user_id}/routine.",
        examples=[False, True],
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must be a non-empty string")
        return value
