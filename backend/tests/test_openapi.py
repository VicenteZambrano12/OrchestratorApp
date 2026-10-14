import json
import os
import subprocess
import sys
import unittest
from dataclasses import fields, is_dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml
from pydantic import TypeAdapter, ValidationError

from api.DataClasses.HealthResponse import HealthResponse
from api.DataClasses.pipeline.ChatRequest import ChatRequest
from api.DataClasses.pipeline.ChatResponse import ChatResponse
from api.documentation import load_app_documentation
from app import app
from utils.routinemaker.dataclass.models import RoutineMakerResult, RoutineParameters


class OpenAPITests(unittest.TestCase):
    def setUp(self):
        self.schema = app.openapi()

    def test_application_metadata_and_tags(self):
        info = self.schema["info"]
        for key in ("title", "summary", "version", "contact", "license"):
            self.assertTrue(info[key])
        self.assertEqual(info["version"], "0.1.0")
        self.assertIn("no authentication", info["description"])
        self.assertIn("plain text", info["description"])
        self.assertEqual(
            {tag["name"] for tag in self.schema["tags"]}, {"Chat", "Health"}
        )
        self.assertTrue(all(tag["description"] for tag in self.schema["tags"]))
        self.assertNotIn("securitySchemes", self.schema["components"])

    def test_app_metadata_matches_yaml(self):
        metadata = load_app_documentation().model_dump()
        info = self.schema["info"]
        for key in ("title", "summary", "version", "description", "contact"):
            self.assertEqual(info[key], metadata[key])
        self.assertEqual(info["license"], metadata["license_info"])
        self.assertEqual(self.schema["tags"], metadata["openapi_tags"])

    def test_metadata_path_is_independent_of_working_directory(self):
        source_path = Path(__file__).resolve().parents[1] / "src"
        with TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import json; from app import app; print(json.dumps(app.openapi()))",
                ],
                cwd=directory,
                env={**os.environ, "PYTHONPATH": str(source_path)},
                capture_output=True,
                text=True,
                check=True,
            )
        self.assertEqual(json.loads(result.stdout), self.schema)

    def test_invalid_or_missing_metadata_fails_explicitly(self):
        valid = load_app_documentation().model_dump()
        for invalid in (
            None,
            [],
            {**valid, "version": 0.1},
            {key: value for key, value in valid.items() if key != "title"},
            {**valid, "debug": True},
        ):
            with self.subTest(metadata=invalid):
                with patch.object(Path, "read_text", return_value=yaml.safe_dump(invalid)):
                    with self.assertRaises(ValidationError):
                        load_app_documentation()
        with patch.object(Path, "read_text", return_value="title: ["):
            with self.assertRaises(yaml.YAMLError):
                load_app_documentation()
        with patch.object(Path, "read_text", side_effect=FileNotFoundError):
            with self.assertRaises(FileNotFoundError):
                load_app_documentation()

    def test_operations_describe_only_existing_behavior(self):
        for path, method, tag, model in (
            ("/{id}/chat", "post", "Chat", "ChatResponse"),
            ("/health", "get", "Health", "HealthResponse"),
        ):
            with self.subTest(path=path):
                operation = self.schema["paths"][path][method]
                self.assertEqual(operation["tags"], [tag])
                self.assertLess(len(operation["summary"].split()), 8)
                self.assertIn("Permissions", operation["description"])
                self.assertIn("Side effects", operation["description"])
                self.assertEqual(
                    operation["responses"]["200"]["content"]["application/json"]["schema"],
                    {"$ref": f"#/components/schemas/{model}"},
                )
                if path == "/health":
                    self.assertNotIn("parameters", operation)
                self.assertNotIn("security", operation)
                for code in ("400", "401", "403", "404"):
                    self.assertNotIn(code, operation["responses"])
                server_error = operation["responses"]["500"]["content"]
                self.assertEqual(set(server_error), {"text/plain"})
                self.assertEqual(
                    server_error["text/plain"]["example"], "Internal Server Error"
                )

        validation = self.schema["paths"]["/{id}/chat"]["post"]["responses"]["422"]
        content = validation["content"]["application/json"]
        self.assertEqual(content["schema"]["required"], ["detail"])
        self.assertEqual(content["example"]["detail"][0]["loc"], ["body", "language"])
        self.assertNotIn("422", self.schema["paths"]["/health"]["get"]["responses"])

    def test_session_id_is_documented_as_required_path_parameter(self):
        self.assertNotIn("/chat", self.schema["paths"])
        operation = self.schema["paths"]["/{id}/chat"]["post"]
        self.assertEqual(len(operation["parameters"]), 1)
        parameter = operation["parameters"][0]
        self.assertEqual(parameter["name"], "id")
        self.assertEqual(parameter["in"], "path")
        self.assertTrue(parameter["required"])
        self.assertEqual(parameter["schema"]["type"], "string")
        self.assertIn("session identifier", parameter["description"])
        self.assertEqual(
            parameter["schema"]["examples"],
            ["session-20261014-morning-workout"],
        )
        self.assertIn("process-local session memory", operation["description"])

    def test_chat_response_requires_selected_subsystem(self):
        schema = self.schema["components"]["schemas"]["ChatResponse"]
        self.assertEqual(set(schema["required"]), {"subsystem", "response"})
        self.assertEqual(
            set(schema["properties"]["subsystem"]["enum"]),
            {"routine_maker", "exercise_explainer", "past_routines_analyzer", "no_system"},
        )
        self.assertEqual(schema["example"]["subsystem"], "exercise_explainer")
        with self.assertRaises(ValidationError):
            ChatResponse(response="Exercise explanation")
        with self.assertRaises(ValidationError):
            ChatResponse(subsystem="custom_system", response="Exercise explanation")

    def test_all_exposed_model_fields_have_valid_examples(self):
        for name, model in (
            ("ChatRequest", ChatRequest),
            ("ChatResponse", ChatResponse),
            ("HealthResponse", HealthResponse),
            ("RoutineParameters", RoutineParameters),
            ("RoutineMakerResult", RoutineMakerResult),
        ):
            with self.subTest(model=name):
                schema = self.schema["components"]["schemas"][name]
                self.assertTrue(schema["description"])
                adapter = TypeAdapter(model)
                adapter.validate_python(schema["example"])
                self.assertEqual(
                    adapter.dump_python(
                        adapter.validate_python(schema["example"]), mode="json", exclude_none=True
                    ),
                    schema["example"],
                )
                for field_name, field in schema["properties"].items():
                    with self.subTest(field=field_name):
                        self.assertTrue(field["description"])
                        self.assertTrue(field["examples"])
                        for example in field["examples"]:
                            payload = {**schema["example"], field_name: example}
                            adapter.validate_python(payload)

    def test_existing_model_contracts_are_preserved(self):
        request = self.schema["components"]["schemas"]["ChatRequest"]
        self.assertEqual(set(request["required"]), {"query", "language"})
        self.assertFalse(request["additionalProperties"])
        self.assertEqual(request["properties"]["query"]["minLength"], 1)
        self.assertEqual(
            ChatRequest(query=" Explain squats ", language="EN").query,
            " Explain squats ",
        )
        parameters = RoutineParameters()
        self.assertEqual(
            parameters.model_dump(),
            {
                "routine_type": None,
                "days_per_week": None,
                "hours_per_session": None,
                "level": None,
            },
        )
        self.assertEqual(
            parameters.missing_fields,
            ("routine_type", "days_per_week", "hours_per_session", "level"),
        )
        self.assertTrue(is_dataclass(RoutineMakerResult))
        self.assertTrue(RoutineMakerResult.__dataclass_params__.frozen)
        self.assertEqual(
            [field.name for field in fields(RoutineMakerResult)],
            ["status", "parameters", "message", "routine", "routine_id"],
        )
        result = RoutineMakerResult(
            "needs_parameters", parameters, "What is your training level?", None
        )
        self.assertIs(result.parameters, parameters)
        self.assertEqual(
            set(self.schema["components"]["schemas"]["RoutineMakerResult"]["required"]),
            {"status", "parameters", "message", "routine"},
        )


if __name__ == "__main__":
    unittest.main()
