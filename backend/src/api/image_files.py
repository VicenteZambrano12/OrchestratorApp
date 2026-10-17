from email.utils import format_datetime
import logging
import mimetypes
import os
from pathlib import Path, PurePosixPath
import re

from dotenv import dotenv_values
from google.api_core.exceptions import GoogleAPIError, NotFound, RetryError
from google.auth.exceptions import DefaultCredentialsError, RefreshError
from google.cloud import storage
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import NotModifiedResponse, StaticFiles
from starlette.datastructures import Headers
from starlette.types import Scope

from config.runtime import runtime_mode


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"
logger = logging.getLogger(__name__)


class CloudImageFiles(StaticFiles):
    def __init__(self, bucket_name: str) -> None:
        super().__init__(check_dir=False)
        self.bucket_name = bucket_name
        self._client: storage.Client | None = None

    async def get_response(self, path: str, scope: Scope) -> Response:
        if scope["method"] not in ("GET", "HEAD"):
            raise HTTPException(status_code=405)
        if (
            not path or path.startswith("/") or "\\" in path or "\x00" in path
            or any(part in (".", "..") for part in PurePosixPath(path).parts)
        ):
            raise HTTPException(status_code=404)
        return await run_in_threadpool(self._response, path, scope)

    def _response(self, path: str, scope: Scope) -> Response:
        try:
            if self._client is None:
                self._client = storage.Client()
            blob = self._client.bucket(self.bucket_name).get_blob(f"images/{path}", timeout=30)
            if blob is None:
                raise HTTPException(status_code=404)
            headers = {"cache-control": blob.cache_control or "public, max-age=3600"}
            if blob.etag:
                headers["etag"] = '"' + blob.etag.strip('"') + '"'
            if blob.updated:
                headers["last-modified"] = format_datetime(blob.updated, usegmt=True)
            if self.is_not_modified(Headers(headers), Headers(scope=scope)):
                return NotModifiedResponse(headers)
            if blob.size is not None:
                headers["content-length"] = str(blob.size)
            if blob.content_encoding:
                headers["content-encoding"] = blob.content_encoding
            content = b"" if scope["method"] == "HEAD" else blob.download_as_bytes(
                timeout=30, if_generation_match=blob.generation, raw_download=True,
            )
            return Response(
                content, headers=headers,
                media_type=blob.content_type or mimetypes.guess_type(path)[0] or "application/octet-stream",
            )
        except NotFound as error:
            raise HTTPException(status_code=404) from error
        except (GoogleAPIError, RetryError, DefaultCredentialsError, RefreshError) as error:
            logger.exception("Unable to retrieve exercise image from Cloud Storage.")
            raise HTTPException(status_code=503, detail="Image storage is unavailable.") from error


def create_image_files() -> StaticFiles:
    settings = dotenv_values(ENV_FILE, interpolate=False) if ENV_FILE.exists() else {}
    if runtime_mode(settings) == "LOCAL":
        return StaticFiles(directory=PROJECT_ROOT / "database/images")
    bucket = (os.environ.get(
        "GCS_IMAGES_BUCKET", settings.get("GCS_IMAGES_BUCKET", "orch_app_bucket"),
    ) or "").strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]", bucket):
        raise ValueError("GCS_IMAGES_BUCKET must be a valid bucket name, not a URL or path.")
    return CloudImageFiles(bucket)
