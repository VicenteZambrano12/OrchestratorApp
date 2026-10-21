"""Serve the built frontend and orchestration API from one ASGI application.

Runtime secrets are loaded before importing the backend composition root because
provider selection can occur during module initialization. The outer application
mounts the backend at ``/api`` and static frontend assets at ``/``; OpenAPI remains
owned by the mounted backend rather than duplicated on the outer application.
Running this script starts Uvicorn using the validated PORT setting.
"""

import json
import os
from pathlib import Path
import re

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn

from obervability.logger import Logger


FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend/dist"
logger = Logger.get_logger(__name__)


def load_runtime_secrets() -> None:
    """Load optional JSON environment settings without overriding existing values.

    Returns:
        None: Populates missing environment variables, or does nothing when
            APP_SECRETS_FILE is unset.

    Raises:
        ValueError: The filename is blank, JSON is invalid, or setting names
            and values are not valid environment entries.
        OSError: The configured secrets file cannot be read.
    """
    # 1. Treat an unset secrets file as optional, but reject a blank configuration.
    filename = os.environ.get("APP_SECRETS_FILE")
    if filename is None:
        return
    if not filename.strip():
        raise ValueError("APP_SECRETS_FILE must not be empty.")
    # 2. Validate the entire document before publishing any environment settings.
    try:
        contents: object = json.loads(Path(filename).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("APP_SECRETS_FILE must contain a UTF-8 JSON object.") from None
    if not isinstance(contents, dict):
        raise ValueError("APP_SECRETS_FILE must contain a JSON object of environment settings.")
    settings: dict[str, str] = {}
    for key, value in contents.items():
        if (
            not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key)
            or not isinstance(value, str) or "\x00" in value
        ):
            raise ValueError("APP_SECRETS_FILE requires valid environment names and string values.")
        settings[key] = value
    # 3. Preserve deployment-provided overrides when applying file-based secrets.
    for key, value in settings.items():
        os.environ.setdefault(key, value)
    logger.debug("Runtime secrets loaded")


def create_app() -> FastAPI:
    """Build the combined frontend and backend application.

    Returns:
        FastAPI: Outer ASGI app with the API and static frontend mounts.

    Raises:
        ValueError: Runtime secrets or logging configuration are invalid.
        OSError: A configured secrets file cannot be read.
        RuntimeError: The frontend build is missing.
        Exception: Backend import or initialization errors propagate unchanged.
    """
    # 1. Resolve secrets and logging before imports select backend providers.
    load_runtime_secrets()
    Logger.configure()
    from app import app as backend_app

    # 2. Require a complete frontend build rather than serving a partial deployment.
    if not (FRONTEND_DIR / "index.html").is_file():
        logger.error("Combined server startup failed reason=missing_frontend_build")
        raise RuntimeError("Frontend build is missing; run npm run build in frontend first.")
    # 3. Mount the API first so the root static mount cannot intercept API paths.
    application = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
    application.mount("/api", backend_app)
    application.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    logger.info("Combined frontend and backend application initialized")
    return application


def listen_port() -> int:
    """Resolve the network port for the combined server.

    Returns:
        int: PORT in the inclusive range 1 to 65535, defaulting to 8080.

    Raises:
        ValueError: PORT is not an integer in the supported range.
    """
    # 1. Reject invalid deployment settings before starting the listener.
    try:
        port = int(os.environ.get("PORT", "8080"))
    except ValueError:
        raise ValueError("PORT must be an integer from 1 to 65535.") from None
    # 2. Enforce the TCP port range after numeric parsing.
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be an integer from 1 to 65535.")
    return port


if __name__ == "__main__":
    uvicorn.run(create_app(), host="0.0.0.0", port=listen_port())
