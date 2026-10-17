import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi import FastAPI

import server


class RuntimeConfigurationTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.file = Path(directory.name) / "secrets.json"
        env = patch.dict(os.environ, {"APP_SECRETS_FILE": str(self.file)}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def test_mounted_json_is_loaded_without_overriding_explicit_environment(self):
        self.file.write_text(json.dumps({
            "MODE": "CLOUD", "GEMINI_API_KEY": "private-test-value", "PORT": "8080",
        }), encoding="utf-8")
        with patch.dict(os.environ, {"PORT": "9090"}):
            server.load_runtime_secrets()
            self.assertEqual(os.environ["MODE"], "CLOUD")
            self.assertEqual(os.environ["GEMINI_API_KEY"], "private-test-value")
            self.assertEqual(server.listen_port(), 9090)

    def test_environment_only_startup_does_not_require_a_secret_file(self):
        with patch.dict(os.environ, {}, clear=True):
            server.load_runtime_secrets()
            self.assertEqual(server.listen_port(), 8080)

    def test_invalid_json_configuration_is_rejected_without_revealing_values(self):
        for contents in (
            "private-test-value", "[]", "null",
            '{"GEMINI_API_KEY": "private-test-value", "BAD": null}',
            '{"GEMINI_API_KEY": "private-test-value", "INVALID=KEY": "x"}',
            '{"GEMINI_API_KEY": "private-test-value", "BAD": "\\u0000"}',
        ):
            with self.subTest(contents=contents):
                self.file.write_text(contents, encoding="utf-8")
                with self.assertRaises(ValueError) as raised:
                    server.load_runtime_secrets()
                self.assertNotIn("private-test-value", str(raised.exception))
                self.assertNotIn("GEMINI_API_KEY", os.environ)

    def test_missing_or_empty_secret_file_setting_fails_explicitly(self):
        with self.assertRaises(FileNotFoundError):
            server.load_runtime_secrets()
        with patch.dict(os.environ, {"APP_SECRETS_FILE": ""}):
            with self.assertRaisesRegex(ValueError, "APP_SECRETS_FILE"):
                server.load_runtime_secrets()

    def test_invalid_ports_are_rejected(self):
        for value in ("", "not-a-port", "0", "-1", "65536"):
            with self.subTest(value=value), patch.dict(os.environ, {"PORT": value}):
                with self.assertRaisesRegex(ValueError, "PORT"):
                    server.listen_port()


class CombinedServerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.frontend = Path(directory.name)
        (self.frontend / "index.html").write_text("<html>Frontend fixture</html>", encoding="utf-8")
        (self.frontend / "assets").mkdir()
        (self.frontend / "assets/app.js").write_text("console.log('frontend');", encoding="utf-8")
        root_patch = patch.object(server, "FRONTEND_DIR", self.frontend)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        env = patch.dict(os.environ, {"MODE": "LOCAL"}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.app = server.create_app()

    async def request(self, path, method="GET"):
        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        await self.app({
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
            "root_path": "", "query_string": b"", "headers": [],
            "client": ("127.0.0.1", 1234), "server": ("testserver", 80),
        }, receive, send)
        start = next(message for message in messages if message["type"] == "http.response.start")
        body = b"".join(
            message.get("body", b"") for message in messages if message["type"] == "http.response.body"
        )
        return start["status"], dict(start["headers"]), body

    async def test_frontend_index_and_bundled_assets_are_served(self):
        status, headers, body = await self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"text/html", headers[b"content-type"])
        self.assertIn(b"Frontend fixture", body)
        status, _, body = await self.request("/assets/app.js")
        self.assertEqual((status, body), (200, b"console.log('frontend');"))

    async def test_frontend_api_prefix_reaches_the_backend(self):
        status, _, body = await self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"status": "ok"})
        status, _, body = await self.request("/api/openapi.json")
        self.assertEqual(status, 200)
        self.assertIn("/users", json.loads(body)["paths"])
        status, _, body = await self.request("/api/docs")
        self.assertEqual(status, 200)
        self.assertIn(b"/api/openapi.json", body)

    async def test_unknown_api_paths_and_missing_assets_do_not_return_frontend_html(self):
        for path in ("/api/not-an-endpoint", "/assets/missing.js", "/missing"):
            with self.subTest(path=path):
                status, _, body = await self.request(path)
                self.assertEqual(status, 404)
                self.assertNotIn(b"Frontend fixture", body)

    def test_missing_frontend_build_fails_startup(self):
        (self.frontend / "index.html").unlink()
        with self.assertRaisesRegex(RuntimeError, "Frontend build is missing"):
            server.create_app()

    def test_secret_configuration_is_loaded_before_backend_import(self):
        backend = FastAPI()
        marker = []

        class BackendModule:
            def __getattr__(self, name):
                if name == "app":
                    marker.append(os.environ.get("LOADED_FROM_SECRET"))
                    return backend
                raise AttributeError(name)

        secret = self.frontend / "secrets.json"
        secret.write_text('{"LOADED_FROM_SECRET": "yes"}', encoding="utf-8")
        with patch.dict(os.environ, {"APP_SECRETS_FILE": str(secret)}):
            with patch.dict("sys.modules", {"app": BackendModule()}):
                server.create_app()
        self.assertEqual(marker, ["yes"])


if __name__ == "__main__":
    unittest.main()
