import json
import os
from pathlib import Path
import re

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn


FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend/dist"


def load_runtime_secrets() -> None:
    filename = os.environ.get("APP_SECRETS_FILE")
    if filename is None:
        return
    if not filename.strip():
        raise ValueError("APP_SECRETS_FILE must not be empty.")
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
    for key, value in settings.items():
        os.environ.setdefault(key, value)


def create_app() -> FastAPI:
    # Provider selection happens when backend modules are imported.
    load_runtime_secrets()
    from app import app as backend_app

    if not (FRONTEND_DIR / "index.html").is_file():
        raise RuntimeError("Frontend build is missing; run npm run build in frontend first.")
    application = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
    application.mount("/api", backend_app)
    application.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
    return application


def listen_port() -> int:
    try:
        port = int(os.environ.get("PORT", "8080"))
    except ValueError:
        raise ValueError("PORT must be an integer from 1 to 65535.") from None
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be an integer from 1 to 65535.")
    return port


if __name__ == "__main__":
    uvicorn.run(create_app(), host="0.0.0.0", port=listen_port())
