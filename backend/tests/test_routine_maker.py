import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from systems.routinemaker.RoutineMaker import (
    RoutineMaker,
    RoutineMakerResult,
    RoutineParameters,
)
from utils.general.GeminiApiCall import GeminiClient
from utils.routinemaker.generate import generate
from utils.routinemaker.handle import handle
from utils.routinemaker.load_prompts import load_prompts
from utils.routinemaker.models import (
    RoutineMakerResult as UtilityResult,
    RoutineParameters as UtilityParameters,
)


COMPLETE = {
    "routine_type": "ppl",
    "days_per_week": 3,
    "hours_per_session": 1.0,
    "level": "beginner",
}


def decision(intent="create", parameters=None, message=""):
    return json.dumps({
        "intent": intent,
        "parameters": {} if parameters is None else parameters,
        "message": message,
    })


SMOKE_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts_manual_func_tests/test_routine_maker.py"
)
SMOKE_SPEC = importlib.util.spec_from_file_location("routine_maker_smoke_test", SMOKE_SCRIPT)
SMOKE_MODULE = importlib.util.module_from_spec(SMOKE_SPEC)
SMOKE_SPEC.loader.exec_module(SMOKE_MODULE)


class RoutineMakerSmokeTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock(spec=GeminiClient)
        self.client.api_key = "example-key"

    def test_default_query_creates_and_prints_routine(self):
        self.client.generate.side_effect = [decision(parameters=COMPLETE), "New routine"]
        with patch.object(sys, "argv", [str(SMOKE_SCRIPT)]), patch.object(
            SMOKE_MODULE, "GeminiClient", return_value=self.client
        ) as factory, patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(SMOKE_MODULE.main(), 0)
        factory.assert_called_once_with(max_output_tokens=4096)
        self.assertEqual(
            output.getvalue(),
            f"created\nParameters: {RoutineParameters(**COMPLETE).model_dump_json()}\n"
            "New routine\n",
        )
        payload = json.loads(self.client.generate.call_args_list[0].args[0])
        self.assertEqual(
            payload["query"],
            "Make me a beginner routine for three days per week, "
            "one hour per training session.",
        )
        self.assertEqual(payload["language"], "EN")
        self.assertIsNone(payload["routine"])

    def test_custom_query_and_language_collect_missing_parameters(self):
        for language in ("EN", "ES"):
            with self.subTest(language=language):
                self.client.generate.side_effect = [decision(), "Missing requirements?"]
                with patch.object(sys, "argv", [
                    str(SMOKE_SCRIPT), "Make me a routine", "--language", language,
                    "--parameters", '{"routine_type": "weider"}',
                ]), patch.object(
                    SMOKE_MODULE, "GeminiClient", return_value=self.client
                ), patch("sys.stdout", new_callable=io.StringIO) as output:
                    self.assertEqual(SMOKE_MODULE.main(), 0)
                self.assertTrue(output.getvalue().startswith("needs_parameters\n"))
                self.assertTrue(output.getvalue().endswith("Missing requirements?\n"))
                payload = json.loads(self.client.generate.call_args.args[0])
                self.assertEqual(payload["query"], "Make me a routine")
                self.assertEqual(payload["language"], language)
                self.assertEqual(payload["parameters"]["routine_type"], "weider")
                self.assertNotIn("routine_type", payload["missing_parameters"])

    def test_existing_routine_file_and_parameters_reach_updater(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "routine.txt"
            path.write_text("Existing routine", encoding="utf-8")
            self.client.generate.side_effect = [
                decision("update", {"days_per_week": 4}), "Updated routine",
            ]
            with patch.object(sys, "argv", [
                str(SMOKE_SCRIPT), "Change to four days",
                "--parameters", json.dumps(COMPLETE), "--routine-file", str(path),
            ]), patch.object(
                SMOKE_MODULE, "GeminiClient", return_value=self.client
            ), patch("sys.stdout", new_callable=io.StringIO) as output:
                self.assertEqual(SMOKE_MODULE.main(), 0)
        self.assertTrue(output.getvalue().startswith("updated\n"))
        self.assertTrue(output.getvalue().endswith("Updated routine\n"))
        payload = json.loads(self.client.generate.call_args.args[0])
        self.assertEqual(payload["routine"], "Existing routine")
        self.assertEqual(payload["parameters"]["days_per_week"], 4)

    def test_unrelated_request_prints_no_match(self):
        self.client.generate.return_value = decision(
            "no_match", message="I help with routines."
        )
        with patch.object(sys, "argv", [
            str(SMOKE_SCRIPT), "What is the weather?",
        ]), patch.object(
            SMOKE_MODULE, "GeminiClient", return_value=self.client
        ), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(SMOKE_MODULE.main(), 0)
        self.assertTrue(output.getvalue().startswith("no_match\n"))
        self.assertTrue(output.getvalue().endswith("I help with routines.\n"))
        self.client.generate.assert_called_once()

    def test_invalid_parameters_fail_before_creating_client(self):
        for parameters in ("not JSON", "[]", '{"days_per_week": 8}'):
            with self.subTest(parameters=parameters), patch.object(sys, "argv", [
                str(SMOKE_SCRIPT), "--parameters", parameters,
            ]), patch.object(
                SMOKE_MODULE, "GeminiClient"
            ) as factory, patch("sys.stderr", new_callable=io.StringIO) as output:
                self.assertEqual(SMOKE_MODULE.main(), 1)
                factory.assert_not_called()
                self.assertIn("Routine maker test failed:", output.getvalue())

    def test_missing_routine_file_fails_before_creating_client(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.txt"
            with patch.object(sys, "argv", [
                str(SMOKE_SCRIPT), "--routine-file", str(path),
            ]), patch.object(
                SMOKE_MODULE, "GeminiClient"
            ) as factory, patch("sys.stderr", new_callable=io.StringIO) as output:
                self.assertEqual(SMOKE_MODULE.main(), 1)
        factory.assert_not_called()
        self.assertIn("Routine maker test failed:", output.getvalue())

    def test_configuration_failure_is_reported(self):
        with patch.object(sys, "argv", [str(SMOKE_SCRIPT)]), patch.object(
            SMOKE_MODULE, "GeminiClient", side_effect=ValueError("Missing API key")
        ), patch("sys.stderr", new_callable=io.StringIO) as output:
            self.assertEqual(SMOKE_MODULE.main(), 1)
        self.assertIn("Missing API key", output.getvalue())

    def test_api_errors_redact_key_and_return_failure(self):
        error = HTTPError(
            "https://example.com", 429, "Too Many Requests", {},
            io.BytesIO(b'{"error": {"message": "Quota exceeded for example-key"}}'),
        )
        self.client.generate.side_effect = error
        with patch.object(sys, "argv", [str(SMOKE_SCRIPT)]), patch.object(
            SMOKE_MODULE, "GeminiClient", return_value=self.client
        ), patch("sys.stderr", new_callable=io.StringIO) as output:
            self.assertEqual(SMOKE_MODULE.main(), 1)
        self.assertIn("HTTP 429", output.getvalue())
        self.assertIn("[REDACTED]", output.getvalue())
        self.assertNotIn("example-key", output.getvalue())

    def test_provider_and_model_output_errors_are_reported(self):
        for response in (RuntimeError("API unavailable"), "Invalid JSON"):
            with self.subTest(response=response):
                self.client.generate.side_effect = [response]
                with patch.object(sys, "argv", [str(SMOKE_SCRIPT)]), patch.object(
                    SMOKE_MODULE, "GeminiClient", return_value=self.client
                ), patch("sys.stderr", new_callable=io.StringIO) as output:
                    self.assertEqual(SMOKE_MODULE.main(), 1)
                self.assertIn("Routine maker test failed:", output.getvalue())


class RoutineMakerUtilityTests(unittest.TestCase):
    def test_model_imports_remain_compatible(self):
        self.assertIs(RoutineParameters, UtilityParameters)
        self.assertIs(RoutineMakerResult, UtilityResult)

    def test_default_prompt_path_is_independent_of_working_directory(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "src/config/prompts/routinemaker/routinemaker.yaml"
        )
        with patch("os.getcwd", return_value="/"):
            self.assertEqual(load_prompts(), load_prompts(path))

    def test_generation_utility_uses_supplied_prompt_and_strips_text(self):
        client = Mock(spec=GeminiClient)
        client.generate.return_value = " Routine \n"
        self.assertEqual(
            generate(client, {"routine_maker": "Create"}, "routine_maker", {"query": "Hi"}),
            "Routine",
        )
        client.generate.assert_called_once_with(
            json.dumps({"query": "Hi"}), system_prompt="Create",
        )

    def test_handle_utility_runs_conditional_stages(self):
        generate_response = Mock(side_effect=[
            decision(parameters=COMPLETE), "Routine",
        ])
        result = handle(generate_response, "Make a routine")
        self.assertEqual(result.status, "created")
        self.assertIsInstance(result, RoutineMakerResult)
        self.assertEqual(
            [call.args[0] for call in generate_response.call_args_list],
            ["routing", "routine_maker"],
        )


class RoutineMakerTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock(spec=GeminiClient)
        self.maker = RoutineMaker(self.client)

    def test_complete_first_request_creates_routine(self):
        self.client.generate.side_effect = [decision(parameters=COMPLETE), " Routine "]
        result = self.maker.handle("Make a beginner PPL, 3 days, 1 hour per session")
        self.assertEqual(result.status, "created")
        self.assertEqual(result.parameters.model_dump(), COMPLETE)
        self.assertEqual(result.message, "Routine")
        self.assertEqual(result.routine, "Routine")
        self.assertEqual(self.client.generate.call_count, 2)
        calls = self.client.generate.call_args_list
        self.assertEqual(calls[0].kwargs["system_prompt"], self.maker._prompts["routing"])
        self.assertEqual(
            calls[1].kwargs["system_prompt"], self.maker._prompts["routine_maker"]
        )
        self.assertEqual(json.loads(calls[1].args[0])["parameters"], COMPLETE)

    def test_first_request_asks_only_for_missing_parameters(self):
        self.client.generate.side_effect = [
            decision(parameters={"routine_type": "weider"}),
            "How many days, hours per session, and what level?",
        ]
        result = self.maker.handle("Make me a Weider routine")
        self.assertEqual(result.status, "needs_parameters")
        self.assertIsNone(result.routine)
        self.assertEqual(result.parameters.routine_type, "weider")
        call = self.client.generate.call_args_list[1]
        self.assertEqual(call.kwargs["system_prompt"], self.maker._prompts["parameters"])
        self.assertEqual(
            json.loads(call.args[0])["missing_parameters"],
            ["days_per_week", "hours_per_session", "level"],
        )

    def test_follow_up_merges_parameters_and_creates_when_complete(self):
        self.client.generate.side_effect = [
            decision(parameters={"routine_type": "ppl", "days_per_week": 3}),
            "Duration and level?",
            decision(parameters={"hours_per_session": 1.0, "level": "beginner"}),
            "Complete routine",
        ]
        first = self.maker.handle("Make a PPL routine for 3 days")
        result = self.maker.handle(
            "One hour per session, beginner", parameters=first.parameters
        )
        self.assertEqual(result.status, "created")
        self.assertEqual(result.parameters.model_dump(), COMPLETE)
        self.assertEqual(self.client.generate.call_count, 4)
        payload = json.loads(self.client.generate.call_args_list[2].args[0])
        self.assertEqual(payload["parameters"], first.parameters.model_dump())

    def test_update_preserves_existing_context_and_overrides_changed_parameter(self):
        self.client.generate.side_effect = [
            decision("update", {"days_per_week": 4}),
            "Updated routine",
        ]
        result = self.maker.handle(
            "Change to four days", parameters=COMPLETE, routine="Existing routine",
            language="ES",
        )
        self.assertEqual(result.status, "updated")
        self.assertEqual(result.parameters.days_per_week, 4)
        self.assertEqual(result.parameters.level, "beginner")
        self.assertEqual(result.routine, "Updated routine")
        call = self.client.generate.call_args_list[1]
        self.assertEqual(
            call.kwargs["system_prompt"], self.maker._prompts["routine_updater"]
        )
        payload = json.loads(call.args[0])
        self.assertEqual(payload["routine"], "Existing routine")
        self.assertEqual(payload["language"], "ES")
        self.assertEqual(payload["query"], "Change to four days")

    def test_incomplete_update_collects_requirements_then_updates(self):
        self.client.generate.side_effect = [
            decision("update", {"days_per_week": 3}),
            "Which split, duration, and level?",
            decision("update", {
                "routine_type": "ppl", "hours_per_session": 1.0, "level": "beginner",
            }),
            "Updated routine",
        ]
        first = self.maker.handle("Change my routine", routine="Existing routine")
        self.assertEqual(first.status, "needs_parameters")
        self.assertEqual(first.routine, "Existing routine")
        result = self.maker.handle(
            "PPL, one hour, beginner",
            parameters=first.parameters, routine=first.routine,
        )
        self.assertEqual(result.status, "updated")
        self.assertEqual(result.parameters.model_dump(), COMPLETE)

    def test_invalid_replacement_clears_old_value_and_asks_for_it(self):
        self.client.generate.side_effect = [
            decision("update", {"routine_type": None}),
            "Do you want Weider or PPL?",
        ]
        result = self.maker.handle(
            "Change the split to something unsupported",
            parameters=COMPLETE, routine="Existing routine",
        )
        self.assertEqual(result.status, "needs_parameters")
        self.assertIsNone(result.parameters.routine_type)
        self.assertEqual(result.parameters.days_per_week, 3)
        self.assertEqual(result.routine, "Existing routine")
        payload = json.loads(self.client.generate.call_args_list[1].args[0])
        self.assertEqual(payload["missing_parameters"], ["routine_type"])

    def test_create_can_replace_existing_routine(self):
        self.client.generate.side_effect = [decision(parameters=COMPLETE), "New routine"]
        result = self.maker.handle("Make a new routine", routine="Old routine")
        self.assertEqual(result.status, "created")
        self.assertEqual(result.routine, "New routine")

    def test_unrelated_request_does_not_write_or_change_state(self):
        self.client.generate.return_value = decision(
            "no_match", {"days_per_week": 5}, "I help with routines."
        )
        result = self.maker.handle(
            "What is the weather?", parameters=COMPLETE, routine="Existing routine"
        )
        self.assertEqual(result.status, "no_match")
        self.assertEqual(result.message, "I help with routines.")
        self.assertEqual(result.parameters.model_dump(), COMPLETE)
        self.assertEqual(result.routine, "Existing routine")
        self.client.generate.assert_called_once()

    def test_update_requires_existing_routine(self):
        self.client.generate.return_value = decision("update", COMPLETE)
        with self.assertRaisesRegex(ValueError, "existing routine"):
            self.maker.handle("Update my routine", parameters=COMPLETE)
        self.client.generate.assert_called_once()

    def test_invalid_input_does_not_call_api(self):
        for options in (
            {"query": ""},
            {"query": "  "},
            {"query": None},
            {"query": "Make a routine", "language": "FR"},
            {"query": "Make a routine", "routine": ""},
            {"query": "Make a routine", "routine": 123},
            {"query": "Make a routine", "parameters": {"days_per_week": 8}},
            {"query": "Make a routine", "parameters": {"days_per_week": True}},
            {"query": "Make a routine", "parameters": {"hours_per_session": 0}},
            {"query": "Make a routine", "parameters": {"hours_per_session": 25}},
            {"query": "Make a routine", "parameters": {"hours_per_session": float("nan")}},
            {"query": "Make a routine", "parameters": {"routine_type": "unknown"}},
            {"query": "Make a routine", "parameters": {"level": "expert"}},
            {"query": "Make a routine", "parameters": {"unexpected": 1}},
        ):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.maker.handle(**options)
        self.client.generate.assert_not_called()

    def test_invalid_routing_response_does_not_advance(self):
        for response in (
            "not JSON",
            decision("unknown"),
            decision(parameters={"days_per_week": 0}),
            decision(parameters={"hours_per_session": -1}),
            decision("no_match"),
            '{"intent": "create", "parameters": {}}',
            decision()[:-1] + ', "extra": true}',
        ):
            with self.subTest(response=response):
                self.client.generate.reset_mock()
                self.client.generate.return_value = response
                with self.assertRaises(ValueError):
                    self.maker.handle("Make a routine")
                self.client.generate.assert_called_once()

    def test_empty_output_is_an_error_at_every_stage(self):
        for response in ("", "  ", None):
            for parameters in ({}, COMPLETE):
                with self.subTest(response=response, parameters=parameters):
                    self.client.generate.side_effect = [
                        decision(parameters=parameters), response,
                    ]
                    with self.assertRaisesRegex(ValueError, "empty or non-text"):
                        self.maker.handle("Make a routine")
            self.client.generate.side_effect = [response]
            with self.assertRaisesRegex(ValueError, "empty or non-text"):
                self.maker.handle("Make a routine")

    def test_api_errors_propagate_at_both_steps(self):
        for responses in (
            [RuntimeError("API unavailable")],
            [decision(parameters=COMPLETE), RuntimeError("API unavailable")],
        ):
            self.client.generate.side_effect = responses
            with self.assertRaisesRegex(RuntimeError, "API unavailable"):
                self.maker.handle("Make a routine")

    def test_update_empty_output_and_api_errors_propagate(self):
        for response in (" ", RuntimeError("API unavailable")):
            self.client.generate.side_effect = [decision("update"), response]
            with self.subTest(response=response), self.assertRaises(
                (ValueError, RuntimeError)
            ):
                self.maker.handle(
                    "Change the exercises", parameters=COMPLETE,
                    routine="Existing routine",
                )

    def test_prompt_path_and_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prompts.yaml"
            for content in ("[]", "routing: ''", "routing: valid"):
                path.write_text(content, encoding="utf-8")
                with self.subTest(content=content), self.assertRaises(ValueError):
                    RoutineMaker(self.client, path)
            path.write_text(
                "routing: Route\nparameters: Ask\n"
                "routine_maker: Create\nroutine_updater: Update\n",
                encoding="utf-8",
            )
            maker = RoutineMaker(self.client, path)
            self.client.generate.side_effect = [decision(parameters=COMPLETE), "Routine"]
            maker.handle("Make a routine")
            self.assertEqual(
                self.client.generate.call_args_list[0].kwargs["system_prompt"], "Route"
            )
            self.assertEqual(
                self.client.generate.call_args_list[1].kwargs["system_prompt"], "Create"
            )

    def test_default_client_has_sufficient_output_budget(self):
        with patch(
            "systems.routinemaker.RoutineMaker.GeminiClient", return_value=self.client
        ) as factory:
            RoutineMaker()
        factory.assert_called_once_with(max_output_tokens=4096)

    def test_parameter_model_tracks_missing_fields(self):
        self.assertEqual(RoutineParameters(**COMPLETE).missing_fields, ())
        self.assertEqual(
            RoutineParameters(days_per_week=1, hours_per_session=0.25).missing_fields,
            ("routine_type", "level"),
        )


if __name__ == "__main__":
    unittest.main()
