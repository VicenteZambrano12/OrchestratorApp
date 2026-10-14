import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from systems.exercise_explainer.ExerciseExplainer import ExerciseExplainer
from utils.exercise_explainer.func.generate import generate
from utils.exercise_explainer.func.handle import handle
from utils.exercise_explainer.func.load_prompts import load_prompts
from utils.general.GeminiApiCall import GeminiClient


def decision(exercises, message=""):
    return json.dumps({"exercises": exercises, "message": message})


SMOKE_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts_manual_func_tests/test_exercise_explainer.py"
)
SMOKE_SPEC = importlib.util.spec_from_file_location(
    "exercise_explainer_smoke_test", SMOKE_SCRIPT
)
SMOKE_MODULE = importlib.util.module_from_spec(SMOKE_SPEC)
SMOKE_SPEC.loader.exec_module(SMOKE_MODULE)


class ExerciseExplainerSmokeTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock(spec=GeminiClient)
        self.client.api_key = "example-key"

    def test_default_and_custom_queries_print_response(self):
        for arguments, query, language, exercises, text in (
            ([], "Explain how to perform a squat.", "EN", ["Squat"], "Explanation"),
            (
                ["Explain squat and bench press", "--language", "EN"],
                "Explain squat and bench press", "EN", ["Squat", "Bench press"],
                "Two explanations",
            ),
            (
                ["Explica la sentadilla", "--language", "ES"],
                "Explica la sentadilla", "ES", ["Sentadilla"], "Explicacion",
            ),
        ):
            with self.subTest(arguments=arguments):
                self.client.reset_mock()
                self.client.generate.side_effect = [decision(exercises), text]
                with patch.object(sys, "argv", [str(SMOKE_SCRIPT), *arguments]), patch.object(
                    SMOKE_MODULE, "GeminiClient", return_value=self.client
                ) as factory, patch("sys.stdout", new_callable=io.StringIO) as output:
                    self.assertEqual(SMOKE_MODULE.main(), 0)
                factory.assert_called_once_with(max_output_tokens=4096)
                self.assertEqual(output.getvalue(), text + "\n")
                self.assertEqual(self.client.generate.call_count, 2)
                payload = json.loads(self.client.generate.call_args_list[0].args[0])
                self.assertEqual(payload, {"query": query, "language": language})

    def test_missing_names_prints_question_with_one_call(self):
        self.client.generate.return_value = decision([], "Which exercise?")
        with patch.object(sys, "argv", [
            str(SMOKE_SCRIPT), "Explain an exercise",
        ]), patch.object(
            SMOKE_MODULE, "GeminiClient", return_value=self.client
        ), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(SMOKE_MODULE.main(), 0)
        self.assertEqual(output.getvalue(), "Which exercise?\n")
        self.client.generate.assert_called_once()

    def test_configuration_failure_is_reported(self):
        with patch.object(sys, "argv", [str(SMOKE_SCRIPT)]), patch.object(
            SMOKE_MODULE, "GeminiClient", side_effect=ValueError("Missing API key")
        ), patch("sys.stderr", new_callable=io.StringIO) as output:
            self.assertEqual(SMOKE_MODULE.main(), 1)
        self.assertIn("Exercise explainer test failed: Missing API key", output.getvalue())

    def test_api_error_redacts_key_and_returns_failure(self):
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

    def test_invalid_model_output_is_reported(self):
        self.client.generate.return_value = "not JSON"
        with patch.object(sys, "argv", [str(SMOKE_SCRIPT)]), patch.object(
            SMOKE_MODULE, "GeminiClient", return_value=self.client
        ), patch("sys.stderr", new_callable=io.StringIO) as output:
            self.assertEqual(SMOKE_MODULE.main(), 1)
        self.assertIn("Exercise explainer test failed:", output.getvalue())


class ExerciseExplainerTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock(spec=GeminiClient)
        self.explainer = ExerciseExplainer(self.client)

    def test_single_and_multiple_exercises_use_two_calls(self):
        for exercises in (["Squat"], ["Squat", "Bench press"]):
            with self.subTest(exercises=exercises):
                self.client.reset_mock()
                self.client.generate.side_effect = [
                    decision(exercises), " Exercise explanation \n",
                ]
                query = "Explain " + ", ".join(exercises)
                self.assertEqual(self.explainer.handle(query), "Exercise explanation")
                self.assertEqual(self.client.generate.call_count, 2)
                first, second = self.client.generate.call_args_list
                self.assertEqual(
                    json.loads(first.args[0]), {"query": query, "language": "EN"}
                )
                self.assertEqual(
                    json.loads(second.args[0]),
                    {
                        "query": query,
                        "language": "EN",
                        "parameters": {"exercises": exercises},
                    },
                )
                self.assertNotEqual(
                    first.kwargs["system_prompt"], second.kwargs["system_prompt"]
                )

    def test_missing_names_and_unrelated_requests_use_one_call(self):
        for query in ("Explain an exercise", "Train my chest", "What is the weather?"):
            with self.subTest(query=query):
                self.client.reset_mock()
                self.client.generate.return_value = decision(
                    [], " Please provide an exercise name or list. "
                )
                self.assertEqual(
                    self.explainer.handle(query),
                    "Please provide an exercise name or list.",
                )
                self.client.generate.assert_called_once()

    def test_spanish_is_forwarded_to_both_calls(self):
        self.client.generate.side_effect = [
            decision(["Sentadilla"]), "Explicacion",
        ]
        self.assertEqual(
            self.explainer.handle("Explica la sentadilla", language="ES"),
            "Explicacion",
        )
        for call in self.client.generate.call_args_list:
            self.assertEqual(json.loads(call.args[0])["language"], "ES")

    def test_invalid_input_does_not_call_gemini(self):
        for query, language in (("", "EN"), (" ", "EN"), (None, "EN"), ("Squat", "FR")):
            with self.subTest(query=query, language=language):
                with self.assertRaises(ValueError):
                    self.explainer.handle(query, language=language)
        self.client.generate.assert_not_called()

    def test_invalid_first_response_stops_before_explanation(self):
        for response in (
            "not JSON", "[]", "{}", decision("Squat"), decision([1]),
            decision([" "]), decision([], ""), decision(["Squat"], "Unexpected"),
            '{"exercises": ["Squat"], "message": "", "extra": true}',
            "", None,
        ):
            with self.subTest(response=response):
                self.client.reset_mock()
                self.client.generate.return_value = response
                with self.assertRaises(ValueError):
                    self.explainer.handle("Explain squat")
                self.client.generate.assert_called_once()

    def test_invalid_explanation_is_rejected(self):
        for response in (" ", None):
            with self.subTest(response=response):
                self.client.generate.side_effect = [decision(["Squat"]), response]
                with self.assertRaises(ValueError):
                    self.explainer.handle("Explain squat")

    def test_provider_errors_propagate_from_either_call(self):
        error = RuntimeError("Provider unavailable")
        for responses in ([error], [decision(["Squat"]), error]):
            with self.subTest(responses=responses):
                self.client.generate.side_effect = responses
                with self.assertRaisesRegex(RuntimeError, "Provider unavailable"):
                    self.explainer.handle("Explain squat")

    def test_default_client_configuration(self):
        with patch(
            "systems.exercise_explainer.ExerciseExplainer.GeminiClient",
            return_value=self.client,
        ) as factory:
            ExerciseExplainer()
        factory.assert_called_once_with(max_output_tokens=4096)

    def test_custom_prompts_and_invalid_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prompts.yaml"
            path.write_text(
                "parameters: Extract names\nexplanation: Explain names\n",
                encoding="utf-8",
            )
            explainer = ExerciseExplainer(self.client, path)
            self.client.generate.side_effect = [decision(["Squat"]), "Explanation"]
            explainer.handle("Explain squat")
            self.assertEqual(
                [call.kwargs["system_prompt"] for call in self.client.generate.call_args_list],
                ["Extract names", "Explain names"],
            )
            for content in ("[]", "parameters: Extract names", "parameters: ''\nexplanation: x"):
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        ExerciseExplainer(self.client, path)


class ExerciseExplainerUtilityTests(unittest.TestCase):
    def test_prompt_loading_utility_validates_default_and_custom_prompts(self):
        self.assertEqual(set(load_prompts()), {"parameters", "explanation"})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prompts.yaml"
            path.write_text("parameters: Extract\nexplanation: Explain\n", encoding="utf-8")
            self.assertEqual(
                load_prompts(path), {"parameters": "Extract", "explanation": "Explain"}
            )
            path.write_text("parameters: Extract\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_prompts(path)

    def test_generation_utility_serializes_payload_and_validates_text(self):
        client = Mock(spec=GeminiClient)
        client.generate.return_value = " Explanation \n"
        payload = {"query": "Explain squat", "language": "EN"}
        self.assertEqual(
            generate(client, {"explanation": "Explain"}, "explanation", payload),
            "Explanation",
        )
        client.generate.assert_called_once_with(
            json.dumps(payload, ensure_ascii=True), system_prompt="Explain",
            response_mime_type="text/plain",
        )
        for response in (" ", None):
            with self.subTest(response=response):
                client.generate.return_value = response
                with self.assertRaises(ValueError):
                    generate(client, {"explanation": "Explain"}, "explanation", payload)

    def test_handle_utility_runs_conditional_stages(self):
        generate_response = Mock(side_effect=[decision(["Squat"]), "Explanation"])
        self.assertEqual(handle(generate_response, "Explain squat"), "Explanation")
        self.assertEqual(
            [call.args[0] for call in generate_response.call_args_list],
            ["parameters", "explanation"],
        )
        self.assertEqual(
            generate_response.call_args.args[1]["parameters"], {"exercises": ["Squat"]}
        )
        generate_response = Mock(return_value=decision([], "Which exercise?"))
        self.assertEqual(handle(generate_response, "Explain an exercise"), "Which exercise?")
        generate_response.assert_called_once()
        generate_response.reset_mock()
        with self.assertRaises(ValueError):
            handle(generate_response, "")
        generate_response.assert_not_called()


if __name__ == "__main__":
    unittest.main()
