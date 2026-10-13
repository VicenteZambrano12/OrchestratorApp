import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError


SCRIPT = Path(__file__).resolve().parents[2] / "test_gemini.py"
SPEC = importlib.util.spec_from_file_location("gemini_smoke_test", SCRIPT)
CLI_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CLI_MODULE
SPEC.loader.exec_module(CLI_MODULE)
GeminiClient = CLI_MODULE.GeminiClient
MODULE = sys.modules[GeminiClient.__module__]
ORIGINAL_ENV_FILE = MODULE.ENV_FILE


class GeminiClientTests(unittest.TestCase):
    def test_dotenv_path_still_points_to_repository_root(self):
        self.assertEqual(
            ORIGINAL_ENV_FILE,
            SCRIPT.with_name(".env"),
        )

    def setUp(self):
        environment_patch = patch.dict("os.environ", {}, clear=True)
        environment_patch.start()
        self.addCleanup(environment_patch.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.env_file = Path(directory.name) / ".env"
        env_patch = patch.object(MODULE, "ENV_FILE", self.env_file)
        env_patch.start()
        self.addCleanup(env_patch.stop)

    def test_model_from_dotenv_is_used_in_request(self):
        self.env_file.write_text(
            'GEMINI_API_KEY=example-key\nLLM_MODEL=" gemini-3.1-flash-lite "\n',
            encoding="utf-8",
        )
        response = {"candidates": [{"content": {"parts": [{"text": "Hello"}]}}]}
        with patch.object(
            MODULE, "urlopen", return_value=io.BytesIO(json.dumps(response).encode())
        ) as open_url:
            client = GeminiClient()
            self.assertEqual(client.generate("Hi"), "Hello")
        self.assertEqual(client.model, "gemini-3.1-flash-lite")
        self.assertTrue(
            open_url.call_args.args[0].full_url.endswith(
                "/gemini-3.1-flash-lite:generateContent"
            )
        )

    def test_model_precedence(self):
        self.env_file.write_text("LLM_MODEL=dotenv-model\n", encoding="utf-8")
        with patch.dict("os.environ", {"LLM_MODEL": "environment-model"}):
            self.assertEqual(
                GeminiClient(api_key="example-key").model, "environment-model"
            )
            self.assertEqual(
                GeminiClient(api_key="example-key", model="explicit-model").model,
                "explicit-model",
            )

    def test_missing_model_uses_default(self):
        self.assertEqual(
            GeminiClient(api_key="example-key").model, "gemini-2.5-flash-lite"
        )

    def test_blank_dotenv_model_fails(self):
        self.env_file.write_text("LLM_MODEL=\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "LLM_MODEL"):
            GeminiClient(api_key="example-key")

    def test_cli_model_configuration_and_override(self):
        self.env_file.write_text(
            "GEMINI_API_KEY=example-key\nLLM_MODEL=dotenv-model\n", encoding="utf-8"
        )
        for arguments, expected in (
            ([], "dotenv-model"),
            (["--model", "explicit-model"], "explicit-model"),
        ):
            with self.subTest(arguments=arguments), patch.object(
                sys, "argv", [str(SCRIPT), *arguments]
            ), patch.object(
                GeminiClient, "generate", return_value="Hello"
            ), patch("sys.stdout", new_callable=io.StringIO) as output:
                self.assertEqual(CLI_MODULE.main(), 0)
            self.assertIn(f"Model: {expected}\n", output.getvalue())

    def test_key_from_dotenv(self):
        self.env_file.write_text('GEMINI_API_KEY="dotenv-example-key"\n', encoding="utf-8")
        with patch.dict("os.environ", {}, clear=True):
            client = GeminiClient()
        self.assertEqual(client.api_key, "dotenv-example-key")
        self.assertNotIn("dotenv-example-key", repr(client))

    def test_environment_overrides_dotenv(self):
        self.env_file.write_text("GEMINI_API_KEY=dotenv-key\n", encoding="utf-8")
        with patch.dict("os.environ", {"GEMINI_API_KEY": "environment-key"}):
            self.assertEqual(GeminiClient().api_key, "environment-key")

    def test_explicit_key_overrides_dotenv(self):
        self.env_file.write_text("GEMINI_API_KEY=dotenv-key\n", encoding="utf-8")
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(GeminiClient(api_key="explicit-key").api_key, "explicit-key")

    def test_environment_key_is_not_in_repr(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "example-key"}):
            client = GeminiClient()
        self.assertEqual(client.api_key, "example-key")
        self.assertNotIn("example-key", repr(client))

    def test_missing_key(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "GEMINI_API_KEY"):
                GeminiClient()

    def test_invalid_configuration(self):
        for options in ({"model": ""}, {"max_output_tokens": 0}, {"timeout": 0}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                GeminiClient(api_key="example-key", **options)

    def test_text_request_and_response(self):
        response = {
            "candidates": [{
                "content": {"parts": [
                    {"text": "internal", "thought": True},
                    {"text": "Hello"},
                    {"text": " world"},
                ]},
            }],
        }
        with patch.object(
            MODULE, "urlopen", return_value=io.BytesIO(json.dumps(response).encode())
        ) as open_url:
            self.assertEqual(GeminiClient(api_key="example-key").generate("Hi"), "Hello world")
        request = open_url.call_args.args[0]
        self.assertEqual(request.method, "POST")
        self.assertTrue(request.full_url.endswith("/gemini-2.5-flash-lite:generateContent"))
        self.assertNotIn("example-key", request.full_url)
        self.assertEqual(request.get_header("X-goog-api-key"), "example-key")
        payload = json.loads(request.data)
        self.assertEqual(payload["contents"][0]["parts"], [{"text": "Hi"}])
        self.assertEqual(payload["generationConfig"]["maxOutputTokens"], 256)
        self.assertEqual(open_url.call_args.kwargs["timeout"], 30.0)

    def test_empty_prompt_does_not_call_api(self):
        with patch.object(MODULE, "urlopen") as open_url:
            with self.assertRaisesRegex(ValueError, "prompt"):
                GeminiClient(api_key="example-key").generate("  ")
        open_url.assert_not_called()

    def test_system_prompt_is_sent_as_system_instruction(self):
        response = {"candidates": [{"content": {"parts": [{"text": "coding"}]}}]}
        with patch.object(
            MODULE, "urlopen", return_value=io.BytesIO(json.dumps(response).encode())
        ) as open_url:
            self.assertEqual(
                GeminiClient(api_key="example-key").generate(
                    "Fix a bug", system_prompt="Return only a subsystem ID."
                ),
                "coding",
            )
        payload = json.loads(open_url.call_args.args[0].data)
        self.assertEqual(
            payload["systemInstruction"],
            {"parts": [{"text": "Return only a subsystem ID."}]},
        )
        self.assertEqual(payload["contents"][0]["parts"], [{"text": "Fix a bug"}])

    def test_empty_system_prompt_does_not_call_api(self):
        with patch.object(MODULE, "urlopen") as open_url:
            with self.assertRaisesRegex(ValueError, "system_prompt"):
                GeminiClient(api_key="example-key").generate("Hi", system_prompt=" ")
        open_url.assert_not_called()

    def test_blocked_and_empty_responses(self):
        for response, reason in (
            ({"promptFeedback": {"blockReason": "SAFETY"}}, "SAFETY"),
            ({"candidates": [{"finishReason": "SAFETY"}]}, "SAFETY"),
            ({"candidates": [{"content": {"parts": [{"text": "  "}]}}]}, "empty response"),
        ):
            with self.subTest(response=response), patch.object(
                MODULE, "urlopen", return_value=io.BytesIO(json.dumps(response).encode())
            ):
                with self.assertRaisesRegex(RuntimeError, reason):
                    GeminiClient(api_key="example-key").generate("Hi")

    def test_api_errors_propagate(self):
        error = HTTPError("https://example.com", 429, "Too Many Requests", {}, None)
        with patch.object(MODULE, "urlopen", side_effect=error):
            with self.assertRaises(HTTPError):
                GeminiClient(api_key="example-key").generate("Hi")

    def test_list_models_filters_and_paginates(self):
        pages = [
            {
                "models": [
                    {"name": "models/gemini-3.1-flash-lite",
                     "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/embedding",
                     "supportedGenerationMethods": ["embedContent"]},
                ],
                "nextPageToken": "page+2",
            },
            {"models": [
                {"name": "models/gemini-2.5-flash-lite",
                 "supportedGenerationMethods": ["generateContent"]},
            ]},
        ]
        with patch.object(
            MODULE, "urlopen",
            side_effect=[io.BytesIO(json.dumps(page).encode()) for page in pages],
        ) as open_url:
            self.assertEqual(
                GeminiClient(api_key="example-key").list_models(),
                ["gemini-3.1-flash-lite", "gemini-2.5-flash-lite"],
            )
        self.assertEqual(open_url.call_args_list[0].args[0].get_method(), "GET")
        self.assertEqual(
            open_url.call_args.args[0].full_url,
            "https://generativelanguage.googleapis.com/v1beta/models?pageToken=page%2B2",
        )

    def test_list_models_empty_fails(self):
        with patch.object(MODULE, "urlopen", return_value=io.BytesIO(b'{"models": []}')):
            with self.assertRaisesRegex(RuntimeError, "No text-generation models"):
                GeminiClient(api_key="example-key").list_models()

    def test_cli_lists_models_without_generating(self):
        with patch.object(sys, "argv", [str(SCRIPT), "--list-models"]), patch.object(
            GeminiClient, "list_models", return_value=["gemini-3.1-flash-lite"]
        ), patch.object(GeminiClient, "generate") as generate, patch.dict(
            "os.environ", {"GEMINI_API_KEY": "example-key"}
        ), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(CLI_MODULE.main(), 0)
        generate.assert_not_called()
        self.assertEqual(output.getvalue(), "gemini-3.1-flash-lite\n")

    def test_cli_404_reports_details_and_redacts_key(self):
        error = HTTPError(
            "https://example.com", 404, "Not Found", {},
            io.BytesIO(b'{"error": {"message": "model not found for example-key"}}'),
        )
        with patch.object(sys, "argv", [str(SCRIPT)]), patch.object(
            GeminiClient, "generate", side_effect=error
        ), patch.dict("os.environ", {"GEMINI_API_KEY": "example-key"}), patch(
            "sys.stderr", new_callable=io.StringIO
        ) as output:
            self.assertEqual(CLI_MODULE.main(), 1)
        self.assertIn("HTTP 404", output.getvalue())
        self.assertIn("model not found", output.getvalue())
        self.assertIn("--list-models", output.getvalue())
        self.assertNotIn("example-key", output.getvalue())

    def test_cli_success(self):
        with patch.object(sys, "argv", [str(SCRIPT)]), patch.object(
            GeminiClient, "generate", return_value="It works."
        ), patch.dict("os.environ", {"GEMINI_API_KEY": "example-key"}), patch(
            "sys.stdout", new_callable=io.StringIO
        ) as output:
            self.assertEqual(CLI_MODULE.main(), 0)
        self.assertIn("It works.", output.getvalue())

    def test_cli_missing_key_fails(self):
        with patch.object(sys, "argv", [str(SCRIPT)]), patch.dict(
            "os.environ", {}, clear=True
        ), patch("sys.stderr", new_callable=io.StringIO) as output:
            self.assertEqual(CLI_MODULE.main(), 1)
        self.assertIn("GEMINI_API_KEY", output.getvalue())


if __name__ == "__main__":
    unittest.main()
