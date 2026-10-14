import json
import io
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from pydantic import ValidationError

from systems.orch.Orchestrator import Orchestrator
from utils.general.GeminiApiCall import GeminiClient
from utils.orch.func.create_chat_selector import create_chat_selector
from utils.orch.func.create_gemini_chat_model import create_gemini_chat_model
from utils.orch.func.no_system_message import no_system_message
from utils.orch.func.resolve_systems_path import resolve_systems_path
from utils.orch.func.route import route


SMOKE_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts_manual_func_tests/test_orchestrator.py"
)
SMOKE_SPEC = importlib.util.spec_from_file_location("orchestrator_smoke_test", SMOKE_SCRIPT)
SMOKE_MODULE = importlib.util.module_from_spec(SMOKE_SPEC)
SMOKE_SPEC.loader.exec_module(SMOKE_MODULE)


class OrchestratorSmokeTests(unittest.TestCase):
    def test_script_displays_no_system_message_in_selected_language(self):
        for language in ("EN", "ES"):
            with self.subTest(language=language):
                client = GeminiClient(api_key="example-key", model="gemini-3.1-flash-lite")
                with patch.object(sys, "argv", [
                    str(SMOKE_SCRIPT), "What is the capital of Japan?", "--language", language,
                ]), patch.object(
                    SMOKE_MODULE, "GeminiClient", return_value=client
                ), patch.object(
                    client, "generate", return_value="no_system\n"
                ) as generate, patch("sys.stdout", new_callable=io.StringIO) as output:
                    self.assertEqual(SMOKE_MODULE.main(), 0)
                self.assertEqual(
                    output.getvalue(), f"no_system\n{Orchestrator.no_system_message(language)}\n"
                )
                self.assertEqual(json.loads(generate.call_args.args[0])["language"], language)
                generate.assert_called_once()

    def test_script_routes_query_and_prints_selection(self):
        client = GeminiClient(api_key="example-key", model="gemini-3.1-flash-lite")
        with patch.object(sys, "argv", [
            str(SMOKE_SCRIPT), "How do I squat?", "--language", "ES",
        ]), patch.object(
            SMOKE_MODULE, "GeminiClient", return_value=client
        ), patch.object(
            client, "generate", return_value="exercise_explainer\n"
        ) as generate, patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(SMOKE_MODULE.main(), 0)
        self.assertEqual(output.getvalue(), "exercise_explainer\n")
        self.assertEqual(json.loads(generate.call_args.args[0])["language"], "ES")

    def test_script_reports_configuration_failure(self):
        with patch.object(sys, "argv", [str(SMOKE_SCRIPT)]), patch.object(
            SMOKE_MODULE, "GeminiClient", side_effect=ValueError("Missing API key")
        ), patch("sys.stderr", new_callable=io.StringIO) as output:
            self.assertEqual(SMOKE_MODULE.main(), 1)
        self.assertIn("Missing API key", output.getvalue())

    def test_script_reports_api_error_without_key(self):
        from urllib.error import HTTPError

        client = GeminiClient(api_key="example-key", model="gemini-3.1-flash-lite")
        error = HTTPError(
            "https://example.com", 404, "Not Found", {},
            io.BytesIO(b'{"error": {"message": "Unavailable for example-key"}}'),
        )
        with patch.object(sys, "argv", [str(SMOKE_SCRIPT)]), patch.object(
            SMOKE_MODULE, "GeminiClient", return_value=client
        ), patch.object(
            client, "generate", side_effect=error
        ), patch("sys.stderr", new_callable=io.StringIO) as output:
            self.assertEqual(SMOKE_MODULE.main(), 1)
        self.assertIn("HTTP 404", output.getvalue())
        self.assertIn("[REDACTED]", output.getvalue())
        self.assertNotIn("example-key", output.getvalue())


class OrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.selector = Mock(return_value="coding")
        self.orchestrator = Orchestrator(self.selector)
        self.payload = {
            "query": "Fix this Python function",
            "subsystems": [
                {"id": "writing", "description": "Write and edit prose"},
                {
                    "id": "coding",
                    "description": "Write and debug software",
                    "endpoint": "/coding",
                },
            ],
        }

    def test_routing_utilities_can_be_used_directly(self):
        client = Mock(spec=GeminiClient)
        client.generate.return_value = " coding\n"
        selector = create_chat_selector(create_gemini_chat_model(client))

        self.assertEqual(
            route(selector, resolve_systems_path(), self.payload, "ES"), "coding"
        )
        self.assertEqual(
            json.loads(client.generate.call_args.args[0]),
            {**self.payload, "language": "ES"},
        )
        self.assertEqual(no_system_message("ES"), Orchestrator.no_system_message("ES"))

    def test_utility_systems_path_defaults_to_backend_configuration(self):
        expected = Path(__file__).resolve().parents[1] / "src/config/systems.json"
        self.assertEqual(resolve_systems_path(), expected)
        self.assertEqual(resolve_systems_path("custom.json"), Path("custom.json"))

    def test_routes_mapping_and_returns_only_target_id(self):
        result = self.orchestrator.route(self.payload)

        self.assertEqual(result, "coding")
        self.selector.assert_called_once_with(
            self.payload["query"], self.payload["subsystems"], "EN"
        )
        self.assertEqual(self.payload["subsystems"][1]["endpoint"], "/coding")

    def test_no_system_is_valid_even_with_custom_subsystems(self):
        self.selector.return_value = "no_system"
        self.assertEqual(self.orchestrator.route(self.payload), "no_system")
        self.selector.assert_called_once()

    def test_invalid_selection_can_retry_to_no_system(self):
        self.selector.side_effect = ["unknown", "no_system"]
        self.assertEqual(self.orchestrator.route(self.payload), "no_system")
        self.assertEqual(self.selector.call_count, 2)

    def test_no_system_is_not_used_to_hide_invalid_responses(self):
        self.selector.return_value = "no_system or coding"
        with self.assertRaisesRegex(ValueError, "after 3 attempts"):
            self.orchestrator.route(self.payload)
        self.assertEqual(self.selector.call_count, 3)

    def test_no_system_routing_rules_are_sent_to_gemini(self):
        client = Mock(spec=GeminiClient)
        client.generate.return_value = "no_system"
        result = Orchestrator.from_gemini(client).route(
            {"query": "What is the capital of Japan?"}
        )
        self.assertEqual(result, "no_system")
        self.assertIn(
            "If no supplied subsystem can handle the request, output no_system.",
            client.generate.call_args.kwargs["system_prompt"],
        )
        client.generate.assert_called_once()

    def test_no_system_messages_and_invalid_language(self):
        self.assertIn("No available system", Orchestrator.no_system_message("EN"))
        self.assertIn("Ningún sistema", Orchestrator.no_system_message("ES"))
        with self.assertRaisesRegex(ValueError, "language must be"):
            Orchestrator.no_system_message("FR")

    def test_invalid_no_system_message_configuration_is_reported(self):
        for configuration in (
            "[", "[]", "{}", "messages: []", "messages: {EN: null}",
            'messages: {EN: " "}',
        ):
            with self.subTest(configuration=configuration), patch(
                "pathlib.Path.read_text", return_value=configuration
            ):
                with self.assertRaises(ValueError):
                    Orchestrator.no_system_message("EN")

    def test_missing_no_system_message_file_is_reported(self):
        with patch("pathlib.Path.read_text", side_effect=FileNotFoundError):
            with self.assertRaises(FileNotFoundError):
                Orchestrator.no_system_message()

    def test_accepts_serialized_json(self):
        self.assertEqual(
            self.orchestrator.route(json.dumps(self.payload)), "coding"
        )

    def test_rejects_invalid_payload_before_calling_selector(self):
        invalid_payloads = [
            "{",
            "[]",
            None,
            {},
            {**self.payload, "query": " "},
            {**self.payload, "query": 123},
            {**self.payload, "subsystems": []},
            {**self.payload, "subsystems": {}},
            {**self.payload, "subsystems": [None]},
            {**self.payload, "subsystems": [{"id": "coding"}]},
            {**self.payload, "subsystems": [{"id": "", "description": "Code"}]},
            {**self.payload, "subsystems": [{"id": 1, "description": "Code"}]},
            {**self.payload, "subsystems": [{"id": "coding", "description": " "}]},
            {**self.payload, "subsystems": [{"id": "coding", "description": 1}]},
            {**self.payload, "subsystems": [self.payload["subsystems"][0]] * 2},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    self.orchestrator.route(payload)
        self.selector.assert_not_called()

    def test_rejects_unknown_or_invalid_selector_result(self):
        for result in ["missing", None, [], 1]:
            with self.subTest(result=result):
                self.selector.return_value = result
                with self.assertRaises(ValueError):
                    self.orchestrator.route(self.payload)

    def test_propagates_selector_failure(self):
        self.selector.side_effect = RuntimeError("AI provider unavailable")
        with self.assertRaisesRegex(RuntimeError, "AI provider unavailable"):
            self.orchestrator.route(self.payload)

    def test_requires_callable_selector(self):
        with self.assertRaises(TypeError):
            Orchestrator(None)

    def test_invalid_selection_retries_and_returns_second_valid_id(self):
        self.selector.side_effect = ["unknown", "coding"]
        self.assertEqual(self.orchestrator.route(self.payload), "coding")
        self.assertEqual(self.selector.call_count, 2)

    def test_valid_selection_on_third_attempt(self):
        self.selector.side_effect = ["coding, writing", '{"id": "coding"}', "coding"]
        self.assertEqual(self.orchestrator.route(self.payload), "coding")
        self.assertEqual(self.selector.call_count, 3)

    def test_three_invalid_selections_raise_with_pydantic_cause(self):
        self.selector.side_effect = ["unknown", "coding and writing", "Choose coding"]
        with self.assertRaisesRegex(ValueError, "after 3 attempts") as raised:
            self.orchestrator.route(self.payload)
        self.assertEqual(self.selector.call_count, 3)
        self.assertIsInstance(raised.exception.__cause__, ValidationError)

    def test_pydantic_rejects_non_string_and_extra_output(self):
        for result in (None, 1, [], {"id": "coding"}, '"coding"', "coding\nwriting", ""):
            with self.subTest(result=result):
                self.selector.reset_mock()
                self.selector.return_value = result
                with self.assertRaisesRegex(ValueError, "after 3 attempts"):
                    self.orchestrator.route(self.payload)
                self.assertEqual(self.selector.call_count, 3)

    def test_provider_errors_are_not_retried(self):
        self.selector.side_effect = RuntimeError("API unavailable")
        with self.assertRaisesRegex(RuntimeError, "API unavailable"):
            self.orchestrator.route(self.payload)
        self.selector.assert_called_once()

    def test_gemini_invalid_ids_retry_with_same_prompt(self):
        client = Mock(spec=GeminiClient)
        client.generate.side_effect = ["missing", "coding and writing", "coding\n"]
        self.assertEqual(Orchestrator.from_gemini(client).route(self.payload), "coding")
        self.assertEqual(client.generate.call_count, 3)
        self.assertEqual(client.generate.call_args_list[0], client.generate.call_args_list[2])

    def test_gemini_stops_after_three_invalid_ids(self):
        client = Mock(spec=GeminiClient)
        client.generate.return_value = "not-a-system"
        with self.assertRaisesRegex(ValueError, "after 3 attempts"):
            Orchestrator.from_gemini(client).route(self.payload)
        self.assertEqual(client.generate.call_count, 3)

    def test_chat_model_receives_yaml_prompts_and_json_payload(self):
        chat_model = Mock(return_value="coding")
        orchestrator = Orchestrator.from_chat_model(chat_model)

        result = orchestrator.route(self.payload)

        self.assertEqual(result, "coding")
        chat_model.assert_called_once()
        messages = chat_model.call_args.args[0]
        self.assertEqual([message["role"] for message in messages], ["system", "user"])
        self.assertIn("You are the Orchestrator", messages[0]["content"])
        self.assertEqual(json.loads(messages[1]["content"]), {**self.payload, "language": "EN"})

    def test_custom_prompt_path_and_template(self):
        chat_model = Mock(return_value="coding")
        with patch("pathlib.Path.read_text", return_value=(
            'system_prompt: Choose a subsystem\nuser_prompt: "Route: {payload}"\n'
        )) as read_text:
            orchestrator = Orchestrator.from_chat_model(chat_model, "custom.yaml")
        read_text.assert_called_once_with(encoding="utf-8")

        orchestrator.route(self.payload)

        messages = chat_model.call_args.args[0]
        self.assertEqual(messages[0]["content"], "Choose a subsystem")
        self.assertEqual(
            messages[1]["content"], "Route: " + json.dumps({**self.payload, "language": "EN"})
        )

    def test_rejects_invalid_prompt_configuration(self):
        configurations = [
            "[]",
            "{}",
            'system_prompt: " "\nuser_prompt: "{payload}"',
            'system_prompt: Choose\nuser_prompt: 123',
            'system_prompt: Choose\nuser_prompt: Missing placeholder',
            'system_prompt: Choose\nuser_prompt: "{payload} {unknown}"',
        ]
        for configuration in configurations:
            with self.subTest(configuration=configuration):
                with patch("pathlib.Path.read_text", return_value=configuration):
                    with self.assertRaises(ValueError):
                        Orchestrator.from_chat_model(Mock())

    def test_chat_model_selection_is_validated(self):
        orchestrator = Orchestrator.from_chat_model(Mock(return_value="missing"))
        with self.assertRaises(ValueError):
            orchestrator.route(self.payload)

    def test_invalid_payload_is_not_sent_to_chat_model(self):
        chat_model = Mock()
        orchestrator = Orchestrator.from_chat_model(chat_model)
        with self.assertRaises(ValueError):
            orchestrator.route({})
        chat_model.assert_not_called()

    def test_requires_callable_chat_model(self):
        with self.assertRaises(TypeError):
            Orchestrator.from_chat_model(None)

    def test_gemini_receives_system_prompt_and_validated_payload(self):
        client = Mock(spec=GeminiClient)
        client.generate.return_value = " coding\n"
        orchestrator = Orchestrator.from_gemini(client)

        result = orchestrator.route(self.payload, language="ES")

        self.assertEqual(result, "coding")
        client.generate.assert_called_once()
        self.assertEqual(
            json.loads(client.generate.call_args.args[0]),
            {**self.payload, "language": "ES"},
        )
        self.assertIn(
            "You are the Orchestrator", client.generate.call_args.kwargs["system_prompt"]
        )

    def test_gemini_default_client_is_created_once(self):
        with patch("utils.orch.func.create_gemini_chat_model.GeminiClient") as create_client:
            create_client.return_value.generate.return_value = "coding"
            orchestrator = Orchestrator.from_gemini()
            orchestrator.route(self.payload)
            orchestrator.route(self.payload)
        create_client.assert_called_once_with()
        self.assertEqual(create_client.return_value.generate.call_count, 2)

    def test_gemini_custom_configuration_paths(self):
        client = Mock(spec=GeminiClient)
        client.generate.return_value = "coding"
        with patch("pathlib.Path.read_text", return_value=(
            'system_prompt: Choose a subsystem\nuser_prompt: "Route: {payload}"\n'
        )):
            orchestrator = Orchestrator.from_gemini(
                client, prompt_path="custom.yaml", systems_path="custom.json"
            )
        orchestrator.route(self.payload)
        self.assertEqual(orchestrator._systems_path, Path("custom.json"))
        self.assertEqual(
            client.generate.call_args.kwargs["system_prompt"], "Choose a subsystem"
        )
        self.assertEqual(
            client.generate.call_args.args[0],
            "Route: " + json.dumps({**self.payload, "language": "EN"}),
        )

    def test_gemini_invalid_input_and_unknown_selection(self):
        client = Mock(spec=GeminiClient)
        orchestrator = Orchestrator.from_gemini(client)
        with self.assertRaises(ValueError):
            orchestrator.route({})
        client.generate.assert_not_called()
        client.generate.return_value = "missing"
        with self.assertRaises(ValueError):
            orchestrator.route(self.payload)

    def test_gemini_api_failure_propagates(self):
        client = Mock(spec=GeminiClient)
        client.generate.side_effect = RuntimeError("Gemini unavailable")
        with self.assertRaisesRegex(RuntimeError, "Gemini unavailable"):
            Orchestrator.from_gemini(client).route(self.payload)

    def test_gemini_routes_through_actual_client_request(self):
        response = {"candidates": [{"content": {"parts": [{"text": "coding\n"}]}}]}
        client = GeminiClient(api_key="example-key", model="gemini-3.1-flash-lite")
        orchestrator = Orchestrator.from_gemini(client)
        with patch(
            "utils.general.GeminiApiCall.urlopen",
            return_value=io.BytesIO(json.dumps(response).encode()),
        ) as open_url:
            result = orchestrator.route(self.payload)
        self.assertEqual(result, "coding")
        request = open_url.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/gemini-3.1-flash-lite:generateContent"))
        payload = json.loads(request.data)
        self.assertIn("You are the Orchestrator", payload["systemInstruction"]["parts"][0]["text"])
        self.assertEqual(
            json.loads(payload["contents"][0]["parts"][0]["text"]),
            {**self.payload, "language": "EN"},
        )

    def test_query_only_uses_gym_registry_in_model_prompt(self):
        configuration = json.loads(
            (Path(__file__).resolve().parents[1] / "src/config/systems.json").read_text(
                encoding="utf-8"
            )
        )
        queries = [
            "Make a workout routine for me",
            "How do I perform a squat?",
            "Show my past routines and progress",
        ]
        for subsystem, query in zip(configuration["subsystems"], queries):
            with self.subTest(subsystem=subsystem["id"]):
                chat_model = Mock(return_value=subsystem["id"])
                orchestrator = Orchestrator.from_chat_model(chat_model)

                result = orchestrator.route(json.dumps({"query": query}))

                self.assertEqual(result, subsystem["id"])
                messages = chat_model.call_args.args[0]
                self.assertEqual(
                    json.loads(messages[1]["content"]),
                    {"query": query, "subsystems": configuration["subsystems"], "language": "EN"},
                )

    def test_custom_systems_path(self):
        orchestrator = Orchestrator(self.selector, systems_path="gym.json")
        with patch("pathlib.Path.read_text", return_value=json.dumps({
            "subsystems": self.payload["subsystems"]
        })) as read_text:
            result = orchestrator.route({"query": self.payload["query"]})
        self.assertEqual(orchestrator._systems_path, Path("gym.json"))
        read_text.assert_called_once_with(encoding="utf-8")
        self.assertEqual(result, "coding")

    def test_explicit_subsystems_do_not_read_registry(self):
        with patch("pathlib.Path.read_text") as read_text:
            self.orchestrator.route(self.payload)
        read_text.assert_not_called()

    def test_rejects_invalid_systems_configuration(self):
        configurations = [
            "{", "[]", "{}", '{"subsystems": null}', '{"subsystems": []}',
            '{"subsystems": [{"id": "gym"}]}',
            json.dumps({"subsystems": [self.payload["subsystems"][0]] * 2}),
        ]
        for configuration in configurations:
            with self.subTest(configuration=configuration):
                with patch("pathlib.Path.read_text", return_value=configuration):
                    with self.assertRaises(ValueError):
                        self.orchestrator.route({"query": "Create a routine"})
        self.selector.assert_not_called()

    def test_missing_systems_file_is_not_silently_ignored(self):
        with patch("pathlib.Path.read_text", side_effect=FileNotFoundError):
            with self.assertRaises(FileNotFoundError):
                self.orchestrator.route({"query": "Create a routine"})
        self.selector.assert_not_called()

    def test_language_parameter_is_passed_to_selector_with_id_only_result(self):
        for language in ["ES", "EN"]:
            with self.subTest(language=language):
                self.selector.reset_mock()
                result = self.orchestrator.route(self.payload, language=language)
                self.assertEqual(result, "coding")
                self.selector.assert_called_once_with(
                    self.payload["query"], self.payload["subsystems"], language
                )
        self.assertNotIn("language", self.payload["subsystems"][1])

    def test_language_in_json_reaches_chat_model(self):
        chat_model = Mock(return_value="routine_maker")
        orchestrator = Orchestrator.from_chat_model(chat_model)
        result = orchestrator.route(json.dumps({"query": "Make a routine", "language": "ES"}))
        messages = chat_model.call_args.args[0]
        self.assertEqual(json.loads(messages[1]["content"])["language"], "ES")
        self.assertIn("ES means Spanish; EN means English", messages[0]["content"])
        self.assertEqual(result, "routine_maker")

    def test_language_parameter_overrides_payload_language(self):
        result = self.orchestrator.route({**self.payload, "language": "ES"}, language="EN")
        self.assertEqual(result, "coding")
        self.assertEqual(self.selector.call_args.args[2], "EN")

    def test_rejects_unsupported_language_before_calling_selector(self):
        for language in ["FR", "es", "", None, 1, [], {}]:
            with self.subTest(language=language):
                with self.assertRaisesRegex(ValueError, "language must be"):
                    self.orchestrator.route({**self.payload, "language": language})
        self.selector.assert_not_called()

    def test_gym_registry_contains_language_mapping(self):
        configuration = json.loads(
            (Path(__file__).resolve().parents[1] / "src/config/systems.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(configuration["language"], {"ES": "Spanish", "EN": "English"})


if __name__ == "__main__":
    unittest.main()