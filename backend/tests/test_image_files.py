from datetime import datetime, timezone
from pathlib import Path
import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from google.api_core.exceptions import Forbidden, NotFound, ServiceUnavailable
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import storage
from starlette.staticfiles import StaticFiles

from api import image_files


class ImageFilesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "database/images").mkdir(parents=True)
        self.env_file = self.root / ".env"
        for target, value in (
            ("PROJECT_ROOT", self.root), ("ENV_FILE", self.env_file),
        ):
            replacement = patch.object(image_files, target, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        env = patch.dict(os.environ, {"MODE": "CLOUD"}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.content = b"\x89PNG\r\n\x1a\nsynthetic-image"
        self.blob = Mock(spec=storage.Blob)
        self.blob.size = len(self.content)
        self.blob.etag = "test-etag"
        self.blob.updated = datetime(2026, 1, 2, tzinfo=timezone.utc)
        self.blob.cache_control = None
        self.blob.content_type = "image/png"
        self.blob.content_encoding = None
        self.blob.generation = 123
        self.blob.download_as_bytes.return_value = self.content
        self.client = Mock(spec=storage.Client)
        self.client.bucket.return_value.get_blob.return_value = self.blob
        replacement = patch.object(image_files.storage, "Client", return_value=self.client)
        self.client_factory = replacement.start()
        self.addCleanup(replacement.stop)
        self.files = image_files.create_image_files()
        self.app = FastAPI()
        self.app.mount("/database/images", self.files)

    async def request(self, path="/database/images/icon/press.png", method="GET", headers=()):
        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        await self.app(
            {
                "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                "method": method, "scheme": "http", "path": path,
                "raw_path": path.encode(), "root_path": "", "query_string": b"",
                "headers": list(headers), "client": ("127.0.0.1", 1234),
                "server": ("testserver", 80),
            },
            receive, send,
        )
        start = next(message for message in messages if message["type"] == "http.response.start")
        body = b"".join(
            message.get("body", b"") for message in messages if message["type"] == "http.response.body"
        )
        return start["status"], dict(start["headers"]), body

    async def test_cloud_keeps_existing_url_and_reads_only_images_prefix(self):
        status, headers, body = await self.request()
        self.assertEqual((status, body), (200, self.content))
        self.assertEqual(headers[b"content-type"], b"image/png")
        self.assertEqual(headers[b"content-length"], str(len(body)).encode())
        self.assertEqual(headers[b"cache-control"], b"public, max-age=3600")
        self.client.bucket.assert_called_once_with("orch_app_bucket")
        self.client.bucket.return_value.get_blob.assert_called_once_with("images/icon/press.png", timeout=30)
        self.blob.download_as_bytes.assert_called_once_with(
            timeout=30, if_generation_match=123, raw_download=True,
        )

    async def test_nested_media_names_and_spaces_are_preserved(self):
        await self.request("/database/images/media/Bench Press/0.jpg")
        self.client.bucket.return_value.get_blob.assert_called_once_with(
            "images/media/Bench Press/0.jpg", timeout=30,
        )

    async def test_head_checks_metadata_without_downloading_image(self):
        status, headers, body = await self.request(method="HEAD")
        self.assertEqual((status, body), (200, b""))
        self.assertEqual(headers[b"content-length"], str(len(self.content)).encode())
        self.blob.download_as_bytes.assert_not_called()

    async def test_object_encoding_cache_metadata_and_svg_mime_fallback_are_preserved(self):
        self.blob.content_type = None
        self.blob.content_encoding = "gzip"
        self.blob.cache_control = "private, max-age=60"
        status, headers, body = await self.request("/database/images/anatomy/chest.svg")
        self.assertEqual((status, body), (200, self.content))
        self.assertEqual(headers[b"content-type"], b"image/svg+xml")
        self.assertEqual(headers[b"content-encoding"], b"gzip")
        self.assertEqual(headers[b"cache-control"], b"private, max-age=60")

    async def test_conditional_get_uses_etag_and_last_modified_without_download(self):
        for headers in (
            [(b"if-none-match", b'"test-etag"')],
            [(b"if-modified-since", b"Fri, 02 Jan 2026 00:00:00 GMT")],
        ):
            with self.subTest(headers=headers):
                status, _, body = await self.request(headers=headers)
                self.assertEqual((status, body), (304, b""))
        self.blob.download_as_bytes.assert_not_called()

    async def test_missing_objects_and_objects_deleted_during_download_return_404(self):
        self.client.bucket.return_value.get_blob.return_value = None
        self.assertEqual((await self.request())[0], 404)
        self.client.bucket.return_value.get_blob.return_value = self.blob
        self.blob.download_as_bytes.side_effect = NotFound("gone")
        self.assertEqual((await self.request())[0], 404)

    async def test_permission_and_service_errors_are_logged_and_return_503(self):
        for error in (Forbidden("denied"), ServiceUnavailable("unavailable")):
            self.client.bucket.return_value.get_blob.side_effect = error
            with self.subTest(error=error), self.assertLogs(image_files.logger, level="ERROR"):
                status, _, body = await self.request()
            self.assertEqual(status, 503)
            self.assertIn(b"Image storage is unavailable.", body)

    async def test_missing_adc_is_explicit_and_never_falls_back_to_local_images(self):
        (self.root / "database/images/icon").mkdir()
        (self.root / "database/images/icon/press.png").write_bytes(self.content)
        self.client_factory.side_effect = DefaultCredentialsError("missing ADC")
        with self.assertLogs(image_files.logger, level="ERROR"):
            self.assertEqual((await self.request())[0], 503)

    async def test_traversal_and_write_requests_do_not_reach_cloud_storage(self):
        for path in ("/database/images/../private.png", "/database/images/../../private.png",
                     "/database/images/icon\\private.png", "/database/images/icon/\x00.png"):
            with self.subTest(path=path):
                self.assertEqual((await self.request(path))[0], 404)
        for method in ("POST", "PUT", "DELETE"):
            with self.subTest(method=method):
                self.assertEqual((await self.request(method=method))[0], 405)
        self.client_factory.assert_not_called()

    async def test_local_mode_still_serves_local_files_without_cloud_credentials(self):
        (self.root / "database/images/icon").mkdir()
        (self.root / "database/images/icon/press.png").write_bytes(self.content)
        with patch.dict(os.environ, {"MODE": "LOCAL"}):
            files = image_files.create_image_files()
        self.assertIsInstance(files, StaticFiles)
        self.assertNotIsInstance(files, image_files.CloudImageFiles)
        self.app = FastAPI()
        self.app.mount("/database/images", files)
        status, _, body = await self.request()
        self.assertEqual((status, body), (200, self.content))
        self.client_factory.assert_not_called()

    def test_cloud_startup_does_not_require_a_local_images_folder(self):
        (self.root / "database/images").rmdir()
        self.assertIsInstance(image_files.create_image_files(), image_files.CloudImageFiles)
        self.client_factory.assert_not_called()

    def test_dotenv_mode_bucket_and_process_environment_precedence(self):
        self.env_file.write_text("MODE=CLOUD\nGCS_IMAGES_BUCKET=dotenv_bucket\n", encoding="utf-8")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(image_files.create_image_files().bucket_name, "dotenv_bucket")
        with patch.dict(os.environ, {"GCS_IMAGES_BUCKET": "environment_bucket"}):
            self.assertEqual(image_files.create_image_files().bucket_name, "environment_bucket")
        with patch.dict(os.environ, {"MODE": "LOCAL"}):
            self.assertNotIsInstance(image_files.create_image_files(), image_files.CloudImageFiles)

    def test_invalid_configuration_fails_explicitly(self):
        for bucket in ("", "gs://orch_app_bucket", "orch_app_bucket/images", "../other"):
            with self.subTest(bucket=bucket), patch.dict(os.environ, {"GCS_IMAGES_BUCKET": bucket}):
                with self.assertRaisesRegex(ValueError, "GCS_IMAGES_BUCKET"):
                    image_files.create_image_files()
        with patch.dict(os.environ, {"MODE": "typo"}):
            with self.assertRaisesRegex(ValueError, "MODE"):
                image_files.create_image_files()


if __name__ == "__main__":
    unittest.main()
