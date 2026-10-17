from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SaveRoutineRequest(BaseModel):
    """Confirm a specific session/user preview without an LLM call."""

    model_config = ConfigDict(extra="forbid", strict=True)

    user_id: int = Field(gt=0)
    draft_id: str = Field(min_length=1, pattern=r"\S")
    language: Literal["ES", "EN"]
