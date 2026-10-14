from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Application liveness response; does not indicate provider readiness."""

    model_config = ConfigDict(json_schema_extra={"example": {"status": "ok"}})

    status: Literal["ok"] = Field(
        ...,
        description="Application liveness indicator; external services are not checked.",
        examples=["ok"],
    )
