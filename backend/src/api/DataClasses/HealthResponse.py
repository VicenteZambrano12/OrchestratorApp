"""Describe the public liveness payload without implying dependency readiness.

The health endpoint uses this model for response validation and OpenAPI output;
it does not expose provider credentials or trigger model/database checks.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Validate the health endpoint's fixed application-liveness response.

    Attributes:
        status (Literal["ok"]): Application responsiveness indicator only;
            it makes no claim about Gemini, storage, or configuration readiness.
    """

    model_config = ConfigDict(json_schema_extra={"example": {"status": "ok"}})

    status: Literal["ok"] = Field(
        ...,
        description="Application liveness indicator; external services are not checked.",
        examples=["ok"],
    )
