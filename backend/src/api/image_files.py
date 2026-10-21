"""Select local or Cloud Storage delivery for mounted exercise-image requests.

Local mode delegates file serving to Starlette. Cloud mode reads objects beneath
the bucket's ``images/`` prefix and preserves HTTP caching metadata. Blocking
provider work runs in Starlette's thread pool; credentials are resolved by the
Google client, not supplied by API callers.
"""

from email.utils import format_datetime
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
from obervability.logger import Logger


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"
logger = Logger.get_logger(__name__)


class CloudImageFiles(StaticFiles):
    """Adapt Starlette static-file requests to a Google Cloud Storage bucket.

    The application mounts this ASGI handler for image delivery. It validates
    object-relative paths before accessing storage and reuses a lazily created
    provider client. Inherited StaticFiles state supplies request dispatch and
    conditional-request evaluation, without a checked local directory.

    Attributes:
        bucket_name (str): Configured bucket name, without a URL or object prefix.
        _client (storage.Client | None): Lazily initialized Google client shared
            by subsequent requests to this handler.
    """

    def __init__(self, bucket_name: str) -> None:
        """Initialize a cloud handler without contacting the provider.

        Args:
            bucket_name (str): Bucket used for objects under ``images/``.

        Returns:
            None: Initializes static-file dispatch and bucket state without
            creating a cloud client or accessing storage.
        """
        # 1. Retain static-file dispatch while deferring cloud access until a request.
        super().__init__(check_dir=False)
        self.bucket_name = bucket_name
        self._client: storage.Client | None = None

    async def get_response(self, path: str, scope: Scope) -> Response:
        """Serve a safe relative image path using a worker-thread lookup.

        Args:
            path (str): Object-relative image path supplied by StaticFiles.
            scope (Scope): ASGI request scope with method and cache headers.

        Returns:
            Response: HTTP 200 image/HEAD response or HTTP 304 cache response.

        Raises:
            HTTPException: With 405 for unsupported methods, 404 for rejected
                paths or missing objects, or 503 for supported provider failures.
        """
        # 1. Reject unsupported methods and unsafe names before any cloud access.
        if scope["method"] not in ("GET", "HEAD"):
            raise HTTPException(status_code=405)
        if (
            not path or path.startswith("/") or "\\" in path or "\x00" in path
            or any(part in (".", "..") for part in PurePosixPath(path).parts)
        ):
            raise HTTPException(status_code=404)
        # 2. Keep synchronous metadata and download calls off the event loop.
        return await run_in_threadpool(self._response, path, scope)

    @Logger.trace(logger)
    def _response(self, path: str, scope: Scope) -> Response:
        """Resolve object metadata and honor conditional or HEAD image requests.

        Args:
            path (str): Previously checked image path beneath ``images/``.
            scope (Scope): ASGI request scope used for method and cache checks.

        Returns:
            Response: HTTP 304 when validators match; otherwise HTTP 200 with
            object metadata and raw bytes, or an empty body for HEAD.

        Raises:
            HTTPException: With 404 for absent objects or provider NotFound;
                with 503 for Google API, retry, or credential failures.
        """
        # 1. Resolve the object lazily so handler creation needs no credentials.
        try:
            if self._client is None:
                self._client = storage.Client()
            blob = self._client.bucket(self.bucket_name).get_blob(f"images/{path}", timeout=30)
            if blob is None:
                raise HTTPException(status_code=404)
            # 2. Evaluate cache validators before downloading the object body.
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
            # 3. Preserve raw encoding and pin downloads to the metadata generation.
            content = b"" if scope["method"] == "HEAD" else blob.download_as_bytes(
                timeout=30, if_generation_match=blob.generation, raw_download=True,
            )
            return Response(
                content, headers=headers,
                media_type=blob.content_type or mimetypes.guess_type(path)[0] or "application/octet-stream",
            )
        # 4. Keep missing images distinct from credential or storage outages.
        except NotFound as error:
            raise HTTPException(status_code=404) from error
        except (GoogleAPIError, RetryError, DefaultCredentialsError, RefreshError) as error:
            logger.error(
                "Unable to retrieve exercise image from Cloud Storage error_type=%s",
                type(error).__name__,
            )
            raise HTTPException(status_code=503, detail="Image storage is unavailable.") from error


@Logger.trace(logger)
def create_image_files() -> StaticFiles:
    """Build the image mount for the validated deployment mode.

    Environment values take precedence over adjacent project dotenv settings.
    LOCAL serves ``database/images``; CLOUD validates the bucket name before
    creating a lazy CloudImageFiles handler, defaulting to ``orch_app_bucket``.

    Returns:
        StaticFiles: Local filesystem handler or its cloud-backed subclass.

    Raises:
        ValueError: If MODE or the configured cloud bucket name is invalid.
        RuntimeError: If Starlette cannot find the local image directory.
        OSError: If reading configuration or inspecting local storage fails.
    """
    # 1. Select the deployment provider without requiring cloud credentials locally.
    settings = dotenv_values(ENV_FILE, interpolate=False) if ENV_FILE.exists() else {}
    if runtime_mode(settings) == "LOCAL":
        logger.debug("Exercise image storage selected provider=local")
        return StaticFiles(directory=PROJECT_ROOT / "database/images")
    # 2. Accept only a bucket identifier, never a URL or caller-controlled prefix.
    bucket = (os.environ.get(
        "GCS_IMAGES_BUCKET", settings.get("GCS_IMAGES_BUCKET", "orch_app_bucket"),
    ) or "").strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]", bucket):
        raise ValueError("GCS_IMAGES_BUCKET must be a valid bucket name, not a URL or path.")
    logger.debug("Exercise image storage selected provider=gcs")
    return CloudImageFiles(bucket)
