import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from utils.general.GeminiApiCall import GeminiClient
from utils.routinemaker.models import RoutineMakerResult, RoutineParameters


SMOKE_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts_manual_func_tests/test_pipeline.py"
)
SMOKE_SPEC = importlib.util.spec_from_file_location("pipeline_smoke_test", SMOKE_SCRIPT)
SMOKE_MODULE = importlib.util.module_from_spec(SMOKE_SPEC)
SMOKE_SPEC.loader.exec_module(SMOKE_MODULE)


class PipelineSmokeTests(unittest.TestCase):
    def test_script_routes_and_executes_explainer_in_selected_language(self):
        for language in ("EN", "ES"):
            with self.subTest(language=language):
                client = SMOKE_MODULE.TracingGeminiClient(
                    api_key="example-key", model="test-model"
                )
                with patch.object(
                    sys, "argv", [str(SMOKE_SCRIPT), "Explain squats", "--language", language]
                ), patch.object(
                    SMOKE_MODULE, "TracingGeminiClient", return_value=client
                ), patch.object(
                    GeminiClient, "generate",
                    side_effect=[
                        "exercise_explainer",
                        '{"exercises": ["squat"], "message": ""}',
                        "Squat explanation",
                    ],
                ) as generate, patch(
                    "sys.stdout", new_callable=io.StringIO
                ) as output:
                    self.assertEqual(SMOKE_MODULE.main(), 0)
                trace = output.getvalue()
                self.assertTrue(trace.endswith("=== Final result ===\nSquat explanation\n"))
                self.assertIn("Selected system: exercise_explainer", trace)
                self.assertIn("Passing query and language to exercise_explainer.", trace)
                self.assertIn("Pipeline completed: 3 API calls", trace)
                for number in range(1, 4):
                    self.assertIn(f"=== API call {number}:", trace)
                    self.assertIn(f"API call {number} response:", trace)
                    self.assertIn(f"API call {number} duration:", trace)
                self.assertIn("System prompt:", trace)
                self.assertIn("User payload:", trace)
                self.assertEqual(generate.call_count, 3)
                for call in generate.call_args_list:
                    payload = json.loads(call.args[0])
                    self.assertEqual(payload["language"], language)
                    self.assertEqual(payload["query"], "Explain squats")

    def test_script_prints_routine_result(self):
        client = SMOKE_MODULE.TracingGeminiClient(api_key="example-key", model="test-model")
        result = RoutineMakerResult(
            status="created", parameters=RoutineParameters(days_per_week=3),
            message="Your routine", routine="Your routine",
        )
        with patch.object(sys, "argv", [str(SMOKE_SCRIPT)]), patch.object(
            SMOKE_MODULE, "TracingGeminiClient", return_value=client
        ), patch.object(
            SMOKE_MODULE, "Pipeline"
        ) as pipeline, patch("sys.stdout", new_callable=io.StringIO) as output:
            pipeline.return_value.handle.return_value = result
            self.assertEqual(SMOKE_MODULE.main(), 0)
        self.assertTrue(
            output.getvalue().endswith(
                f"created\nParameters: {result.parameters.model_dump_json()}\nYour routine\n"
            )
        )

    def test_script_returns_no_match_without_downstream_api_calls(self):
        client = SMOKE_MODULE.TracingGeminiClient(api_key="example-key", model="test-model")
        with patch.object(
            sys, "argv", [str(SMOKE_SCRIPT), "What is the capital of Japan?", "--language", "ES"]
        ), patch.object(
            SMOKE_MODULE, "TracingGeminiClient", return_value=client
        ), patch.object(
            GeminiClient, "generate", return_value="no_system"
        ) as generate, patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(SMOKE_MODULE.main(), 0)
        self.assertTrue(
            output.getvalue().endswith(
                SMOKE_MODULE.Orchestrator.no_system_message("ES") + "\n"
            )
        )
        self.assertIn("Selected system: no_system", output.getvalue())
        self.assertIn("Pipeline completed: 1 API calls", output.getvalue())
        generate.assert_called_once()

    def test_script_rejects_invalid_parameters_before_creating_client(self):
        with patch.object(
            sys, "argv", [str(SMOKE_SCRIPT), "--parameters", '{"days_per_week": 8}']
        ), patch.object(
            SMOKE_MODULE, "TracingGeminiClient"
        ) as client, patch("sys.stderr", new_callable=io.StringIO) as output:
            self.assertEqual(SMOKE_MODULE.main(), 1)
        client.assert_not_called()
        self.assertIn("Pipeline test failed:", output.getvalue())

    def test_script_reports_api_failure_and_redacts_key(self):
        client = SMOKE_MODULE.TracingGeminiClient(api_key="example-key", model="test-model")
        error = HTTPError(
            "https://example.com", 429, "Too Many Requests", {},
            io.BytesIO(b'{"error": "Quota exceeded for example-key"}'),
        )
        with patch.object(sys, "argv", [str(SMOKE_SCRIPT)]), patch.object(
            SMOKE_MODULE, "TracingGeminiClient", return_value=client
        ), patch.object(
            GeminiClient, "generate", side_effect=error
        ), patch("sys.stderr", new_callable=io.StringIO) as output, patch(
            "sys.stdout", new_callable=io.StringIO
        ):
            self.assertEqual(SMOKE_MODULE.main(), 1)
        self.assertIn("HTTP 429", output.getvalue())
        self.assertIn("[REDACTED]", output.getvalue())
        self.assertNotIn("example-key", output.getvalue())
        self.assertIn("Pipeline stopped after 1 API calls.", output.getvalue())

    def test_trace_redacts_api_key_in_prompts_and_responses(self):
        client = SMOKE_MODULE.TracingGeminiClient(api_key="example-key", model="test-model")
        with patch.object(
            GeminiClient, "generate", return_value="response example-key"
        ), patch("sys.stdout", new_callable=io.StringIO) as output:
            result = client.generate("query example-key", system_prompt="prompt example-key")
        self.assertEqual(result, "response example-key")
        self.assertNotIn("example-key", output.getvalue())
        self.assertEqual(output.getvalue().count("[REDACTED]"), 3)

    def test_trace_includes_routing_retries(self):
        client = SMOKE_MODULE.TracingGeminiClient(api_key="example-key", model="test-model")
        with patch.object(sys, "argv", [str(SMOKE_SCRIPT)]), patch.object(
            SMOKE_MODULE, "TracingGeminiClient", return_value=client
        ), patch.object(
            GeminiClient, "generate", side_effect=["invalid", "no_system"]
        ), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(SMOKE_MODULE.main(), 0)
        trace = output.getvalue()
        self.assertIn("API call 1 response:\ninvalid", trace)
        self.assertIn("API call 2 response:\nno_system", trace)
        self.assertIn("Pipeline completed: 2 API calls", trace)
        self.assertIn("Selected system: no_system", trace)


if __name__ == "__main__":
    unittest.main()
