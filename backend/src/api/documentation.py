"""Load app documentation and describe FastAPI's existing error handling."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict


class AppDocumentation(BaseModel):
    """Validated, documentation-only keyword arguments for the FastAPI app."""

    model_config = ConfigDict(extra="forbid", strict=True)

    title: str
    summary: str
    version: str
    description: str
    contact: dict[str, str]
    license_info: dict[str, str]
    openapi_tags: list[dict[str, str]]


def load_app_documentation() -> AppDocumentation:
    """Load metadata relative to this module; configuration errors propagate."""
    path = Path(__file__).with_suffix(".yaml")
    return AppDocumentation.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )


INTERNAL_SERVER_ERROR_RESPONSE = {
    "description": (
        "Unhandled server failure, including configuration, provider, or processing "
        "errors for chat. Non-debug deployments return plain text, not JSON."
    ),
    "content": {
        "text/plain": {
            "schema": {"type": "string"},
            "example": "Internal Server Error",
        }
    },
}

VALIDATION_ERROR_RESPONSE = {
    "description": (
        "Invalid request body: missing fields, unexpected fields, a blank query, "
        "incorrect types, or a language other than ES or EN."
    ),
    "content": {
        "application/json": {
            "schema": {
                "type": "object",
                "required": ["detail"],
                "properties": {
                    "detail": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["loc", "msg", "type"],
                            "properties": {
                                "loc": {
                                    "type": "array",
                                    "items": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
                                },
                                "msg": {"type": "string"},
                                "type": {"type": "string"},
                                "input": {},
                                "ctx": {"type": "object", "additionalProperties": True},
                            },
                        },
                    }
                },
            },
            "example": {
                "detail": [
                    {
                        "type": "literal_error",
                        "loc": ["body", "language"],
                        "msg": "Input should be 'ES' or 'EN'",
                        "input": "French",
                        "ctx": {"expected": "'ES' or 'EN'"},
                    }
                ]
            },
        }
    },
}
