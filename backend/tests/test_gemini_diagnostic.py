import io
import unittest
from email.message import Message
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from check_gemini_api import PROMPT, main
from utils.general.GeminiApiCall import GeminiClient


class GeminiDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock(spec=GeminiClient)
        self.client.api_key = "diagnostic-test-key"
        self.client.model = "gemini-2.5-flash-lite"
        self.client.generate.return_value = "Gemini connectivity OK"
        client_patch = patch("check_gemini_api.GeminiClient", return_value=self.client)
        self.factory = client_patch.start()
        self.addCleanup(client_patch.stop)
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        for name, stream in (("stdout", self.stdout), ("stderr", self.stderr)):
            stream_patch = patch(f"sys.{name}", stream)
            stream_patch.start()
            self.addCleanup(stream_patch.stop)

    def test_makes_one_dummy_call_and_prints_response(self):
        self.assertEqual(main([]), 0)
        self.factory.assert_called_once_with()
        self.client.generate.assert_called_once_with(PROMPT)
        self.assertIn("Gemini connectivity OK", self.stdout.getvalue())
        self.assertIn("Model: gemini-2.5-flash-lite", self.stdout.getvalue())
        self.assertEqual(self.stderr.getvalue(), "")
        self.assertNotIn(self.client.api_key, self.stdout.getvalue())

    def test_explicit_model_override(self):
        self.assertEqual(main(["--model", "gemini-2.5-flash"]), 0)
        self.factory.assert_called_once_with(model="gemini-2.5-flash")

    def test_provider_errors_show_status_and_body_without_retrying_or_leaking_key(self):
        for code in (401, 429, 503):
            with self.subTest(code=code):
                self.stdout.seek(0)
                self.stdout.truncate()
                self.stderr.seek(0)
                self.stderr.truncate()
                self.client.reset_mock()
                headers = Message()
                headers["Retry-After"] = "30"
                body = io.BytesIO(
                    (
                        '{"error":{"message":"Service unavailable",'
                        f'"diagnostic":"{self.client.api_key}"}}}}'
                    ).encode()
                )
                self.client.generate.side_effect = HTTPError(
                    "https://generativelanguage.googleapis.com/",
                    code, "Provider error", headers, body,
                )
                self.assertEqual(main([]), 1)
                self.assertIn(f"HTTP {code}", self.stderr.getvalue())
                self.assertIn("Service unavailable", self.stderr.getvalue())
                self.assertIn("Retry-After: 30", self.stderr.getvalue())
                self.assertIn("[REDACTED]", self.stderr.getvalue())
                self.assertNotIn(
                    self.client.api_key, self.stdout.getvalue() + self.stderr.getvalue()
                )
                self.client.generate.assert_called_once_with(PROMPT)
                self.assertTrue(body.closed)

    def test_network_timeout_and_invalid_response_fail_explicitly(self):
        for error in (
            URLError("Name resolution failed"),
            TimeoutError("Request timed out"),
            RuntimeError("Gemini returned no text"),
            ValueError("Invalid provider JSON"),
        ):
            with self.subTest(error=error):
                self.client.generate.side_effect = error
                self.assertEqual(main([]), 1)
                self.assertIn(str(error), self.stderr.getvalue())

    def test_missing_configuration_does_not_call_provider(self):
        self.factory.side_effect = ValueError("Set GEMINI_API_KEY in the environment.")
        self.assertEqual(main([]), 1)
        self.assertIn("GEMINI_API_KEY", self.stderr.getvalue())
        self.client.generate.assert_not_called()

    def test_error_body_read_failure_is_reported(self):
        body = Mock()
        body.read.side_effect = OSError("Connection closed while reading error body")
        self.client.generate.side_effect = HTTPError(
            "https://generativelanguage.googleapis.com/",
            503, "Provider unavailable", None, body,
        )
        self.assertEqual(main([]), 1)
        self.assertIn("HTTP 503", self.stderr.getvalue())
        self.assertIn("Could not read provider error body", self.stderr.getvalue())
        body.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
