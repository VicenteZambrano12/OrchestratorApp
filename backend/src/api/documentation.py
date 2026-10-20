"""Load validated FastAPI metadata and reusable OpenAPI error descriptions.

Application startup reads the YAML file adjacent to this module. Endpoints reuse
the response dictionaries to describe existing validation and unhandled failures;
these declarations do not install exception handlers or change runtime status
codes. Chat provider failures are documented, not recovered from here.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from obervability.logger import Logger


logger = Logger.get_logger(__name__)


class AppDocumentation(BaseModel):
    """Validate documentation keyword arguments consumed by application setup.

    Strict field validation prevents unintended application options from entering
    through the metadata file; unknown keys are rejected.

    Attributes:
        title (str): Display name of the API.
        summary (str): Short application description.
        version (str): Published API version string.
        description (str): Extended API documentation.
        contact (dict[str, str]): Contact metadata passed to FastAPI.
        license_info (dict[str, str]): License metadata passed to FastAPI.
        openapi_tags (list[dict[str, str]]): Ordered tag metadata for endpoint
            organization in generated documentation.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    title: str
    summary: str
    version: str
    description: str
    contact: dict[str, str]
    license_info: dict[str, str]
    openapi_tags: list[dict[str, str]]


@Logger.trace(logger)
def load_app_documentation() -> AppDocumentation:
    """Read and validate application metadata from the adjacent YAML file.

    Returns:
        AppDocumentation: Strictly validated FastAPI documentation arguments.

    Raises:
        OSError: If the metadata file cannot be read.
        UnicodeError: If its contents cannot be decoded as UTF-8.
        yaml.YAMLError: If the document is not valid YAML.
        pydantic.ValidationError: If metadata has missing, extra, or invalid
            fields. Startup callers receive these errors without fallback.
    """
    # 1. Resolve metadata beside the module, independent of the working directory.
    path = Path(__file__).with_suffix(".yaml")
    # 2. Validate before exposing configuration to FastAPI application setup.
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
