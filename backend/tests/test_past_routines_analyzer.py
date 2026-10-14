import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from systems.past_routines_analyzer.PastRoutinesAnalyzer import PastRoutinesAnalyzer
from utils.general.GeminiApiCall import GeminiClient
from utils.past_routines_analyzer.generate import generate
from utils.past_routines_analyzer.handle import handle
from utils.past_routines_analyzer.load_prompts import load_prompts


HISTORY = (
    "2026-10-01: Squat, 3 sets of 8 reps each at 60 kg.\n"
    "2026-10-08: Squat, 3 sets of 8 reps each at 65 kg."
)
SMOKE_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts_manual_func_tests/test_past_routines_analyzer.py"
)
SMOKE_SPEC = importlib.util.spec_from_file_location(
    "past_routines_analyzer_smoke_test", SMOKE_SCRIPT
)
SMOKE_MODULE = importlib.util.module_from_spec(SMOKE_SPEC)
SMOKE_SPEC.loader.exec_module(SMOKE_MODULE)


def decision(status="ready", message=""):
    return json.dumps({"status": status, "message": message})


class PastRoutinesAnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock(spec=GeminiClient)
        self.analyzer = PastRoutinesAnalyzer(self.client)

    def test_history_request_uses_two_calls_and_preserves_payload(self):
        for language in ("EN", "ES"):
            with self.subTest(language=language):
                self.client.reset_mock()
                self.client.generate.side_effect = [decision(), " Analysis \n"]
                self.assertEqual(
                    self.analyzer.handle(
                        "Compare my workouts", history=HISTORY, language=language
                    ),
                    "Analysis",
                )
                self.assertEqual(self.client.generate.call_count, 2)
                first, second = self.client.generate.call_args_list
                for call in (first, second):
                    self.assertEqual(
                        json.loads(call.args[0]),
                        {
                            "query": "Compare my workouts",
                            "language": language,
                            "history": HISTORY,
                        },
                    )
                self.assertNotEqual(
                    first.kwargs["system_prompt"], second.kwargs["system_prompt"]
                )

    def test_missing_or_insufficient_history_uses_one_call(self):
        for history in (None, "I went to the gym"):
            with self.subTest(history=history):
                self.client.reset_mock()
                self.client.generate.return_value = decision(
                    "needs_history", " Please provide workout records. "
                )
                self.assertEqual(
                    self.analyzer.handle("Analyze my progress", history=history),
                    "Please provide workout records.",
                )
                self.client.generate.assert_called_once()

    def test_unrelated_query_uses_one_call_even_with_history(self):
        self.client.generate.return_value = decision(
            "no_match", "I help review past workouts."
        )
        self.assertEqual(
            self.analyzer.handle("Make a new routine", history=HISTORY),
            "I help review past workouts.",
        )
        self.client.generate.assert_called_once()

    def test_single_session_can_be_summarized(self):
        self.client.generate.side_effect = [decision(), "Single session summary"]
        self.assertEqual(
            self.analyzer.handle(
                "Summarize this workout",
                history="Squat: 3 sets of 8 reps each.",
            ),
            "Single session summary",
        )
        self.assertEqual(self.client.generate.call_count, 2)

    def test_invalid_input_never_calls_gemini(self):
        for query, history, language in (
            ("", HISTORY, "EN"), (None, HISTORY, "EN"),
            ("Analyze", "", "EN"), ("Analyze", " ", "EN"),
            ("Analyze", [], "EN"), ("Analyze", HISTORY, "FR"),
        ):
            with self.subTest(query=query, history=history, language=language):
                with self.assertRaises(ValueError):
                    self.analyzer.handle(query, history=history, language=language)
        self.client.generate.assert_not_called()

    def test_invalid_decisions_stop_before_analysis(self):
        for response in (
            "not JSON", "[]", "{}", decision("unknown"),
            decision("needs_history"), decision("no_match"),
            decision("ready", "Unexpected message"),
            '{"status": "ready", "message": 1}',
            '{"status": "ready", "message": "", "extra": true}',
            "", None,
        ):
            with self.subTest(response=response):
                self.client.reset_mock()
                self.client.generate.return_value = response
                with self.assertRaises(ValueError):
                    self.analyzer.handle("Analyze", history=HISTORY)
                self.client.generate.assert_called_once()

    def test_model_cannot_analyze_without_supplied_history(self):
        self.client.generate.return_value = decision()
        with self.assertRaisesRegex(ValueError, "requires supplied history"):
            self.analyzer.handle("Analyze my progress")
        self.client.generate.assert_called_once()

    def test_invalid_analysis_is_rejected(self):
        for response in (" ", None):
            with self.subTest(response=response):
                self.client.generate.side_effect = [decision(), response]
                with self.assertRaises(ValueError):
                    self.analyzer.handle("Analyze", history=HISTORY)

    def test_provider_errors_propagate_from_either_call(self):
        error = RuntimeError("Provider unavailable")
        for responses in ([error], [decision(), error]):
            with self.subTest(responses=responses):
                self.client.generate.side_effect = responses
                with self.assertRaisesRegex(RuntimeError, "Provider unavailable"):
                    self.analyzer.handle("Analyze", history=HISTORY)

    def test_default_client_configuration(self):
        with patch(
            "systems.past_routines_analyzer.PastRoutinesAnalyzer.GeminiClient",
            return_value=self.client,
        ) as factory:
            PastRoutinesAnalyzer()
        factory.assert_called_once_with(max_output_tokens=4096)

    def test_custom_prompts_and_invalid_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prompts.yaml"
            path.write_text(
                "parameters: Check history\nanalysis: Analyze history\n",
                encoding="utf-8",
            )
            analyzer = PastRoutinesAnalyzer(self.client, path)
            self.client.generate.side_effect = [decision(), "Analysis"]
            analyzer.handle("Analyze", history=HISTORY)
            self.assertEqual(
                [call.kwargs["system_prompt"] for call in self.client.generate.call_args_list],
                ["Check history", "Analyze history"],
            )
            for content in ("[]", "parameters: x", "parameters: ''\nanalysis: x"):
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        PastRoutinesAnalyzer(self.client, path)


class PastRoutinesAnalyzerUtilityTests(unittest.TestCase):
    def test_prompt_loading_utility_validates_default_and_custom_prompts(self):
        self.assertEqual(set(load_prompts()), {"parameters", "analysis"})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prompts.yaml"
            path.write_text("parameters: Check\nanalysis: Analyze\n", encoding="utf-8")
            self.assertEqual(
                load_prompts(path), {"parameters": "Check", "analysis": "Analyze"}
            )
            path.write_text("parameters: Check\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_prompts(path)

    def test_generation_utility_serializes_payload_and_validates_text(self):
        client = Mock(spec=GeminiClient)
        client.generate.return_value = " Analysis \n"
        payload = {"query": "Analyze", "history": HISTORY, "language": "EN"}
        self.assertEqual(
            generate(client, {"analysis": "Analyze"}, "analysis", payload), "Analysis"
        )
        client.generate.assert_called_once_with(
            json.dumps(payload, ensure_ascii=True), system_prompt="Analyze"
        )
        for response in (" ", None):
            with self.subTest(response=response):
                client.generate.return_value = response
                with self.assertRaises(ValueError):
                    generate(client, {"analysis": "Analyze"}, "analysis", payload)

    def test_handle_utility_runs_conditional_stages(self):
        generate_response = Mock(side_effect=[decision(), "Analysis"])
        self.assertEqual(
            handle(generate_response, "Analyze", history=HISTORY), "Analysis"
        )
        self.assertEqual(
            [call.args[0] for call in generate_response.call_args_list],
            ["parameters", "analysis"],
        )
        self.assertEqual(generate_response.call_args.args[1]["history"], HISTORY)
        generate_response = Mock(return_value=decision("needs_history", "Provide history."))
        self.assertEqual(handle(generate_response, "Analyze"), "Provide history.")
        generate_response.assert_called_once()
        generate_response.reset_mock()
        with self.assertRaises(ValueError):
            handle(generate_response, "")
        generate_response.assert_not_called()


class PastRoutinesAnalyzerSmokeTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock(spec=GeminiClient)
        self.client.api_key = "example-key"

    def test_bundled_sample_file_reaches_analyzer(self):
        path = SMOKE_SCRIPT.parent / "fixtures/past_routines_history.txt"
        history = path.read_text(encoding="utf-8")
        self.assertIn("Synthetic workout history", history)
        self.assertIn("60 kg", history)
        self.assertIn("65 kg", history)
        self.client.generate.side_effect = [decision(), "Sample analysis"]
        with patch.object(sys, "argv", [
            str(SMOKE_SCRIPT), "Compare my squat progress",
            "--history-file", str(path), "--language", "EN",
        ]), patch.object(
            SMOKE_MODULE, "GeminiClient", return_value=self.client
        ), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(SMOKE_MODULE.main(), 0)
        self.assertEqual(output.getvalue(), "Sample analysis\n")
        self.assertEqual(self.client.generate.call_count, 2)
        self.assertEqual(
            json.loads(self.client.generate.call_args.args[0])["history"], history
        )

    def test_history_file_and_language_reach_analyzer(self):
        for language in ("EN", "ES"):
            with self.subTest(language=language), tempfile.TemporaryDirectory() as directory:
                self.client.reset_mock()
                path = Path(directory) / "history.txt"
                path.write_text(HISTORY, encoding="utf-8")
                self.client.generate.side_effect = [decision(), "Analysis"]
                with patch.object(sys, "argv", [
                    str(SMOKE_SCRIPT), "Compare my workouts",
                    "--history-file", str(path), "--language", language,
                ]), patch.object(
                    SMOKE_MODULE, "GeminiClient", return_value=self.client
                ) as factory, patch("sys.stdout", new_callable=io.StringIO) as output:
                    self.assertEqual(SMOKE_MODULE.main(), 0)
                factory.assert_called_once_with(max_output_tokens=4096)
                self.assertEqual(output.getvalue(), "Analysis\n")
                self.assertEqual(self.client.generate.call_count, 2)
                self.assertEqual(
                    json.loads(self.client.generate.call_args.args[0]),
                    {
                        "query": "Compare my workouts",
                        "language": language,
                        "history": HISTORY,
                    },
                )

    def test_default_query_without_file_requests_history(self):
        self.client.generate.return_value = decision("needs_history", "Provide history.")
        with patch.object(sys, "argv", [str(SMOKE_SCRIPT)]), patch.object(
            SMOKE_MODULE, "GeminiClient", return_value=self.client
        ), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(SMOKE_MODULE.main(), 0)
        self.assertEqual(output.getvalue(), "Provide history.\n")
        self.client.generate.assert_called_once()
        self.assertEqual(
            json.loads(self.client.generate.call_args.args[0]),
            {
                "query": "Summarize my past workouts and analyze my progress.",
                "language": "EN",
                "history": None,
            },
        )

    def test_missing_empty_or_invalid_utf8_file_fails_before_client(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.txt"
            for content in (None, b" ", b"\xff"):
                with self.subTest(content=content):
                    if content is not None:
                        path.write_bytes(content)
                    with patch.object(sys, "argv", [
                        str(SMOKE_SCRIPT), "--history-file", str(path),
                    ]), patch.object(
                        SMOKE_MODULE, "GeminiClient"
                    ) as factory, patch("sys.stderr", new_callable=io.StringIO) as output:
                        self.assertEqual(SMOKE_MODULE.main(), 1)
                    factory.assert_not_called()
                    self.assertIn("Past routines analyzer test failed:", output.getvalue())

    def test_configuration_and_invalid_output_errors_are_reported(self):
        with patch.object(sys, "argv", [str(SMOKE_SCRIPT)]), patch.object(
            SMOKE_MODULE, "GeminiClient", side_effect=ValueError("Missing API key")
        ), patch("sys.stderr", new_callable=io.StringIO) as output:
            self.assertEqual(SMOKE_MODULE.main(), 1)
        self.assertIn("Missing API key", output.getvalue())
        self.client.generate.return_value = "not JSON"
        with patch.object(sys, "argv", [str(SMOKE_SCRIPT)]), patch.object(
            SMOKE_MODULE, "GeminiClient", return_value=self.client
        ), patch("sys.stderr", new_callable=io.StringIO) as output:
            self.assertEqual(SMOKE_MODULE.main(), 1)
        self.assertIn("Past routines analyzer test failed:", output.getvalue())

    def test_api_errors_redact_key_and_return_failure(self):
        self.client.generate.side_effect = HTTPError(
            "https://example.com", 429, "Too Many Requests", {},
            io.BytesIO(b'{"error": {"message": "Quota exceeded for example-key"}}'),
        )
        with patch.object(sys, "argv", [str(SMOKE_SCRIPT)]), patch.object(
            SMOKE_MODULE, "GeminiClient", return_value=self.client
        ), patch("sys.stderr", new_callable=io.StringIO) as output:
            self.assertEqual(SMOKE_MODULE.main(), 1)
        self.assertIn("HTTP 429", output.getvalue())
        self.assertIn("[REDACTED]", output.getvalue())
        self.assertNotIn(self.client.api_key, output.getvalue())


if __name__ == "__main__":
    unittest.main()
