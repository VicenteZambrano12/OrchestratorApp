from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    """A stateless gym-assistance question with an explicit response language."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        json_schema_extra={
            "example": {
                "query": "Explain how to perform a barbell squat safely.",
                "language": "EN",
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

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must be a non-empty string")
        return value
