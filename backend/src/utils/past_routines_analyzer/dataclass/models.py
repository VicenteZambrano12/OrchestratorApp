from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictStr


class _HistoryDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["ready", "needs_history", "no_match"]
    message: StrictStr
