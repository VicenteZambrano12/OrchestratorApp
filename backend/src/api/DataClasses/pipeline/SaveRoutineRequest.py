"""Validate direct confirmation of a server-cached routine preview.

The chat save endpoint combines this body with its session path parameter.
Clients identify a preview rather than submitting generated plan contents;
confirmation bypasses routing, system prompts, and LLM calls.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SaveRoutineRequest(BaseModel):
    """Identify a user-scoped preview for deterministic confirmation.

    Extra fields and type coercion are forbidden. The save helper verifies the
    user and matches the draft against cached state before persistence.

    Attributes:
        user_id (int): Positive existing database user ID, not authentication.
        draft_id (str): Nonempty preview identifier containing non-whitespace.
        language (Literal["ES", "EN"]): Language of the save confirmation.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    user_id: int = Field(gt=0)
    draft_id: str = Field(min_length=1, pattern=r"\S")
    language: Literal["ES", "EN"]
