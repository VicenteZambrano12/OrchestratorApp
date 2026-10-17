from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictStr, StringConstraints


class ExerciseExplanation(BaseModel):
    """Unmodified catalog values plus a separately generated explanation."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: int
    name: str
    description: str | None
    instructions: str
    icon_url: str | None
    anatomy_diagram_url: str | None
    media_urls: list[str] | None = Field(default=None, min_length=2, max_length=2)
    llm_explanation: Annotated[str, StringConstraints(min_length=1)]


class _ExerciseDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    exercises: list[
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    ]
    message: StrictStr
