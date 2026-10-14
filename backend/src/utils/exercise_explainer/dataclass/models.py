from typing import Annotated

from pydantic import BaseModel, ConfigDict, StrictStr, StringConstraints


class _ExerciseDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    exercises: list[
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    ]
    message: StrictStr
