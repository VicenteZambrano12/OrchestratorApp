"""Strict boundaries for exercise extraction and database-grounded explanations.

The extraction model controls clarification versus catalog lookup. The public
model preserves catalog fields separately from generated prose and rejects
unexpected fields instead of accepting invented exercise metadata.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictStr, StringConstraints


class ExerciseExplanation(BaseModel):
    """Carry catalog facts alongside the provider's nonempty explanation.

    Attributes:
        id (int): Catalog exercise identifier.
        name (str): Catalog display name.
        description (str | None): Optional catalog description.
        instructions (str): Catalog execution instructions.
        icon_url (str | None): Optional icon location.
        anatomy_diagram_url (str | None): Optional anatomy image location.
        media_urls (list[str] | None): Exactly two media paths when supplied.
        llm_explanation (Annotated[str, StringConstraints(min_length=1)]):
            Generated prose; workflow code additionally rejects blank text.
    """

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
    """Parse the name-extraction stage before any catalog access.

    Attributes:
        exercises (list[Annotated[str, StringConstraints(
            strip_whitespace=True, min_length=1)]]): Trimmed nonempty names.
        message (StrictStr): Clarification text for an empty exercise list;
            the handler requires it to be empty when names are present.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    exercises: list[
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    ]
    message: StrictStr
