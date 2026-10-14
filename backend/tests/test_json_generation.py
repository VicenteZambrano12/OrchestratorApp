import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from pydantic import ValidationError

from systems.exercise_explainer.ExerciseExplainer import ExerciseExplainer
from systems.past_routines_analyzer.PastRoutinesAnalyzer import PastRoutinesAnalyzer
from systems.routinemaker.RoutineMaker import RoutineMaker
from utils.exercise_explainer.func.generate import generate as generate_exercise
from utils.general.GeminiApiCall import GeminiClient
from utils.past_routines_analyzer.func.generate import generate as generate_history
from utils.routinemaker.func.generate import generate as generate_routine


CLIENT_MODULE = "utils.general.GeminiApiCall"


def provider_response(text):
    return io.BytesIO(json.dumps({
        "candidates": [{"content": {"parts": [{"text": text}]}}],
    }).encode())


class JSONGenerationTests(unittest.TestCase):
    def setUp(self):
        self.client = GeminiClient(api_key="offline-test-key")

    def test_default_output_remains_text(self):
        with patch(f"{CLIENT_MODULE}.urlopen", return_value=provider_response("Answer")) as request:
            self.assertEqual(self.client.generate("Explain squats"), "Answer")
        self.assertEqual(
            json.loads(request.call_args.args[0].data)["generationConfig"]["responseMimeType"],
            "text/plain",
        )

    def test_all_structured_stages_request_json_and_other_stages_remain_text(self):
        for generate, stages, json_stage in (
            (generate_exercise, ("parameters", "explanation"), "parameters"),
            (generate_history, ("parameters", "analysis"), "parameters"),
            (
                generate_routine,
                ("routing", "parameters", "routine_maker", "routine_updater"),
                "routing",
            ),
        ):
            for stage in stages:
                with self.subTest(generate=generate.__module__, stage=stage):
                    with patch(
                        f"{CLIENT_MODULE}.urlopen",
                        return_value=provider_response('{"message":"Ready"}'),
                    ) as request:
                        generate(self.client, {stage: "Stage instructions"}, stage, {"query": "Gym question"})
                    payload = json.loads(request.call_args.args[0].data)
                    self.assertEqual(
                        payload["generationConfig"]["responseMimeType"],
                        "application/json" if stage == json_stage else "text/plain",
                    )
                    self.assertEqual(
                        payload["systemInstruction"]["parts"][0]["text"],
                        "Stage instructions",
                    )

    def test_exercise_flow_no_longer_requests_fenced_json(self):
        decisions = {"exercises": ["Squat"], "message": ""}

        def respond(request, *, timeout):
            payload = json.loads(request.data)
            user_payload = json.loads(payload["contents"][0]["parts"][0]["text"])
            if "parameters" in user_payload:
                return provider_response("Keep your heels grounded during the squat.")
            text = json.dumps(decisions)
            if payload["generationConfig"]["responseMimeType"] != "application/json":
                text = f"```json\n{text}\n```"
            return provider_response(text)

        with patch(f"{CLIENT_MODULE}.urlopen", side_effect=respond) as request:
            answer = ExerciseExplainer(self.client).handle("Explain how to perform a squat")
        self.assertEqual(answer, "Keep your heels grounded during the squat.")
        self.assertEqual(request.call_count, 2)

    def test_history_and_routine_decisions_still_validate_and_return_original_results(self):
        for system, query, decision, expected in (
            (
                PastRoutinesAnalyzer(self.client),
                "Analyze my progress",
                {"status": "needs_history", "message": "Please provide workout records."},
                "Please provide workout records.",
            ),
            (
                RoutineMaker(self.client),
                "Create a workout routine",
                {"intent": "no_match", "parameters": {}, "message": "Please describe your workout goal."},
                "Please describe your workout goal.",
            ),
        ):
            with self.subTest(system=type(system).__name__):
                with patch(
                    f"{CLIENT_MODULE}.urlopen",
                    return_value=provider_response(json.dumps(decision)),
                ) as request:
                    result = system.handle(query)
                self.assertEqual(
                    result if isinstance(result, str) else result.message, expected
                )
                self.assertEqual(request.call_count, 1)

    def test_invalid_json_is_not_silently_repaired(self):
        for text in ("not JSON", '```json\n{"exercises":["Squat"],"message":""}\n```'):
            with self.subTest(text=text), patch(
                f"{CLIENT_MODULE}.urlopen", return_value=provider_response(text)
            ) as request:
                with self.assertRaises(ValidationError):
                    ExerciseExplainer(self.client).handle("Explain squat")
                self.assertEqual(request.call_count, 1)

    def test_provider_failure_still_propagates_without_retries(self):
        error = HTTPError(
            "https://generativelanguage.googleapis.com/", 503, "Unavailable", None, None
        )
        with patch(f"{CLIENT_MODULE}.urlopen", side_effect=error) as request:
            with self.assertRaises(HTTPError) as caught:
                self.client.generate("Extract exercises", response_mime_type="application/json")
        self.assertIs(caught.exception, error)
        self.assertEqual(request.call_count, 1)

    def test_invalid_output_mode_fails_before_network_call(self):
        with patch(f"{CLIENT_MODULE}.urlopen") as request:
            with self.assertRaisesRegex(ValueError, "response_mime_type"):
                self.client.generate("Explain squats", response_mime_type="text/html")
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
