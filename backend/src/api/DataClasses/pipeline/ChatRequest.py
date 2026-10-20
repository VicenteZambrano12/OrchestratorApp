"""Validate caller input before chat routing or streaming begins.

The API forwards the original query and requested language to the pipeline.
Subsystems own prompt construction, catalog/database tools, and generated
answers; this body neither accepts explicit history nor configures tools.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    """Describe a gym question and the optional context for user-scoped systems.

    Strict validation rejects unknown fields and coercion. Past-routine analysis
    and Routine Maker require an existing user downstream; exercise explanations
    can run without one. The session identifier comes from the endpoint path.

    Attributes:
        query (str): Nonblank question; original surrounding whitespace remains.
        language (Literal["ES", "EN"]): Case-sensitive response-language code.
        user_id (int | None): Positive database user ID or None; not a credential.
        client_saves_routine (bool): Whether routine confirmation should return
            ``save_requested`` for a client PUT instead of persisting directly.
    """

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
        description="Existing database user ID. Required when routed to Routine Maker or Past Routines Analyzer; not authentication.",
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
        """Reject whitespace-only questions without normalizing valid input.

        Args:
            value (str): Query after Pydantic's string and length checks.

        Returns:
            str: The original query, including surrounding whitespace.

        Raises:
            ValueError: If the query contains no non-whitespace characters.
        """
        # 1. Validate usability without changing the text sent to the agents.
        if not value.strip():
            raise ValueError("query must be a non-empty string")
        return value
