import json
import unittest
from unittest.mock import Mock

from api.Endpoint.chat import get_pipeline
from app import app
from systems.orch.Orchestrator import Orchestrator
from systems.pipeline.Pipeline import Pipeline
from utils.pipeline.dataclass.models import PipelineResult
from utils.routinemaker.dataclass.models import RoutineMakerResult, RoutineParameters
from utils.exercise_explainer.dataclass.models import ExerciseExplanation
from systems.exercise_explainer.ExerciseExplainer import ExerciseExplainer
from utils.general.GeminiApiCall import GeminiClient
from systems.routinemaker.RoutineMaker import RoutineMaker
from api.redis_deps import GetNTurns, SetTurn
import test_routine_maker as routine_fixtures


class ChatEndpointTests(unittest.IsolatedAsyncioTestCase):
    chat_path = "/session-20261014-morning-workout/chat"
    session_id = "session-20261014-morning-workout"

    def setUp(self):
        self.pipeline = Mock(spec=Pipeline)
        app.dependency_overrides[get_pipeline] = lambda: self.pipeline
        self.addCleanup(app.dependency_overrides.pop, get_pipeline)

    async def request(self, method, path, payload=None, expected_error=None):
        path, _, query = path.partition("?")
        body = json.dumps(payload).encode("utf-8") if payload is not None else b""
        messages = []

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            messages.append(message)

        call = app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": method,
                "scheme": "http",
                "path": path,
                "raw_path": path.encode("utf-8"),
                "query_string": query.encode("utf-8"),
                "headers": [(b"content-type", b"application/json")],
                "client": ("127.0.0.1", 12345),
                "server": ("testserver", 80),
                "root_path": "",
            },
            receive,
            send,
        )
        if expected_error is None:
            await call
        else:
            with self.assertRaises(expected_error):
                await call
        status = next(
            message["status"]
            for message in messages if message["type"] == "http.response.start"
        )
        response_body = b"".join(
            message.get("body", b"")
            for message in messages if message["type"] == "http.response.body"
        )
        headers = next(
            message["headers"]
            for message in messages if message["type"] == "http.response.start"
        )
        content_type = dict(headers).get(b"content-type", b"")
        result = (
            json.loads(response_body)
            if b"application/json" in content_type
            else response_body.decode("utf-8")
        )
        return status, result

    async def test_returns_text_and_passes_both_fields_unchanged(self):
        for language in ("ES", "EN"):
            with self.subTest(language=language):
                self.pipeline.reset_mock()
                self.pipeline.handle_with_subsystem.return_value = PipelineResult(
                    subsystem="exercise_explainer", response="Exercise explanation"
                )
                status, result = await self.request(
                    "POST", self.chat_path, {"query": " Explain squats ", "language": language}
                )
                self.assertEqual(status, 200)
                self.assertEqual(result, {
                    "subsystem": "exercise_explainer", "response": "Exercise explanation"
                })
                self.pipeline.handle_with_subsystem.assert_called_once_with(
                    " Explain squats ", language, session_id=self.session_id
                )
                self.pipeline.handle.assert_not_called()

    async def test_returns_structured_routine_result(self):
        parameters = RoutineParameters(days_per_week=3)
        self.pipeline.handle_with_subsystem.return_value = PipelineResult(
            subsystem="routine_maker",
            response=RoutineMakerResult(
                status="needs_parameters", parameters=parameters,
                message="What is your level?", routine=None,
            ),
        )
        status, result = await self.request(
            "POST", self.chat_path, {"query": "Create a routine", "language": "EN"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(result, {
            "subsystem": "routine_maker",
            "response": {
                "status": "needs_parameters",
                "parameters": parameters.model_dump(),
                "message": "What is your level?",
                "routine": None,
                "routine_id": None,
            },
        })

    async def test_returns_original_exercise_fields_and_generated_explanation(self):
        exercise = ExerciseExplanation(
            id=1, name="Barbell Bench Press", description=" Original \n",
            instructions="1. Setup.\n2. Press.", icon_url=None,
            anatomy_diagram_url="database/images/anatomy/anatomy_chest.svg",
            media_urls=["database/images/media/Press/0.jpg", "database/images/media/Press/1.jpg"],
            llm_explanation="Keep control. Which step needs more detail?",
        )
        self.pipeline.handle_with_subsystem.return_value = PipelineResult(
            subsystem="exercise_explainer", response=[exercise],
        )
        status, result = await self.request(
            "POST", self.chat_path, {"query": "Explain bench", "language": "EN"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["response"], [exercise.model_dump()])

    async def test_routine_parameters_preview_and_confirmation_survive_http_requests(self):
        fixture = routine_fixtures.RoutineMakerTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.client.generate.side_effect = [
            routine_fixtures.decision(parameters={"routine_type": "ppl"}),
            "How many days, how long and what level?",
            routine_fixtures.decision(parameters={
                "days_per_week": 3, "hours_per_session": 1.0, "level": "beginner",
            }),
            json.dumps(routine_fixtures.plan()),
            routine_fixtures.decision("save"),
        ]
        orchestrator = Mock(spec=Orchestrator)
        orchestrator.route.return_value = "routine_maker"

        def pipeline():
            return Pipeline(
                orchestrator,
                routine_maker=RoutineMaker(
                    fixture.client, database_path=fixture.database, state_store=fixture.store,
                ),
                turn_setter=SetTurn(fixture.store), turn_getter=GetNTurns(fixture.store),
            )

        app.dependency_overrides[get_pipeline] = pipeline
        for query, outcome in (
            ("Make a PPL routine", "needs_parameters"),
            ("Three days, one hour, beginner", "awaiting_confirmation"),
            ("Yes, save it", "saved"),
        ):
            status, body = await self.request("POST", self.chat_path, {
                "query": query, "language": "EN", "user_id": 1,
            })
            self.assertEqual(status, 200)
            self.assertEqual(body["response"]["status"], outcome)
            self.assertEqual(len(fixture.rows()), 1 if outcome == "saved" else 0)
        self.assertEqual(body["response"]["routine"]["days"][0]["day_type"], "push")
        self.assertEqual(body["response"]["routine"]["days"][0]["exercises"][0]["name"], "Bench Press")
        self.assertEqual(fixture.store.turn_count(self.session_id), 3)
        self.assertEqual(orchestrator.route.call_count, 3)
        self.assertEqual(len(orchestrator.route.call_args.args[0]["memory"]), 2)

    async def test_routine_requests_require_user_identity(self):
        orchestrator = Mock(spec=Orchestrator)
        orchestrator.route.return_value = "routine_maker"
        app.dependency_overrides[get_pipeline] = lambda: Pipeline(orchestrator)
        status, body = await self.request("POST", self.chat_path, {
            "query": "Make a routine", "language": "EN",
        })
        self.assertEqual(status, 422)
        self.assertEqual(body["detail"][0]["loc"], ["body", "user_id"])
        self.assertIn("require user_id", body["detail"][0]["msg"])

    async def test_real_catalog_workflow_reaches_the_http_response(self):
        client = Mock(spec=GeminiClient)
        client.generate.side_effect = [
            json.dumps({"exercises": ["barbel bench pres", "Face Pull"], "message": ""}),
            "Press with control. Tell me which step needs more detail.",
            "Pull with control. Tell me which step needs more detail.",
        ]
        orchestrator = Mock(spec=Orchestrator)
        orchestrator.route.return_value = "exercise_explainer"
        pipeline = Pipeline(orchestrator, exercise_explainer=ExerciseExplainer(client))
        app.dependency_overrides[get_pipeline] = lambda: pipeline
        status, result = await self.request(
            "POST", self.chat_path,
            {"query": "Explain barbel bench pres and Face Pull", "language": "EN"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            [exercise["name"] for exercise in result["response"]],
            ["Barbell Bench Press", "Face Pull"],
        )
        self.assertEqual(client.generate.call_count, 3)
        self.assertEqual(len(result["response"][0]["media_urls"]), 2)

    async def test_catalog_images_are_served_without_exposing_other_database_files(self):
        status, body = await self.request("GET", "/database/images/anatomy/anatomy_chest.svg")
        self.assertEqual(status, 200)
        self.assertIn("<svg", body)
        for path in ("/database/gym_app.db", "/database/images/../gym_app.db"):
            status, _ = await self.request("GET", path)
            self.assertEqual(status, 404)

    async def test_returns_no_match_message(self):
        self.pipeline.handle_with_subsystem.return_value = PipelineResult(
            subsystem="no_system", response="No matching system"
        )
        status, result = await self.request(
            "POST", self.chat_path, {"query": "Unrelated question", "language": "EN"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(result, {"subsystem": "no_system", "response": "No matching system"})

    async def test_subsystem_matches_actual_pipeline_routing(self):
        for target in (
            "routine_maker", "exercise_explainer", "past_routines_analyzer", "no_system"
        ):
            for language in ("ES", "EN"):
                with self.subTest(target=target, language=language):
                    orchestrator = Mock(spec=Orchestrator)
                    orchestrator.route.return_value = target
                    orchestrator.no_system_message.return_value = (
                        Orchestrator.no_system_message(language)
                    )
                    system = Mock()
                    if target == "routine_maker":
                        parameters = RoutineParameters(days_per_week=3)
                        system.handle.return_value = RoutineMakerResult(
                            "needs_parameters", parameters, "What is your level?", None
                        )
                        expected = {
                            "status": "needs_parameters",
                            "parameters": parameters.model_dump(),
                            "message": "What is your level?",
                            "routine": None,
                            "routine_id": None,
                        }
                    else:
                        system.handle.return_value = "Exercise explanation"
                        expected = (
                            Orchestrator.no_system_message(language)
                            if target == "no_system"
                            else "Exercise explanation"
                        )
                    pipeline = Pipeline(
                        orchestrator,
                        routine_maker=system,
                        exercise_explainer=system,
                        past_routines_analyzer=system,
                    )
                    app.dependency_overrides[get_pipeline] = lambda: pipeline
                    status, result = await self.request(
                        "POST", self.chat_path,
                        {"query": "My gym question", "language": language, "user_id": 1},
                    )
                    self.assertEqual(status, 200)
                    self.assertEqual(result, {"subsystem": target, "response": expected})
                    orchestrator.route.assert_called_once_with(
                        {"query": "My gym question"}, language=language
                    )
                    self.assertEqual(
                        system.handle.call_count, 0 if target == "no_system" else 1
                    )

    async def test_rejects_invalid_or_extra_fields_before_calling_pipeline(self):
        payloads = [
            {},
            {"query": "Explain squats"},
            {"language": "EN"},
            {"query": "", "language": "EN"},
            {"query": "  ", "language": "ES"},
            {"query": 123, "language": "EN"},
            {"query": None, "language": "EN"},
            {"query": "Explain squats", "language": "en"},
            {"query": "Explain squats", "language": "FR"},
            {"query": "Explain squats", "language": None},
            {"query": "Explain squats", "language": "EN", "history": "Workout"},
            {"query": "Explain squats", "language": "EN", "id": "session-morning-workout"},
            {"query": "Explain squats", "language": "EN", "subsystem": "routine_maker"},
            {"query": "Make a routine", "language": "EN", "user_id": True},
            {"query": "Make a routine", "language": "EN", "user_id": 0},
            {"query": "Make a routine", "language": "EN", "user_id": "1"},
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                status, result = await self.request("POST", self.chat_path, payload)
                self.assertEqual(status, 422)
                self.assertIn("detail", result)
        self.pipeline.handle_with_subsystem.assert_not_called()

    async def test_session_id_is_required_in_path(self):
        for path in ("/chat", "//chat"):
            with self.subTest(path=path):
                status, result = await self.request(
                    "POST", path, {"query": "Explain squats", "language": "EN"}
                )
                self.assertEqual(status, 404)
                self.assertEqual(result, {"detail": "Not Found"})
        self.pipeline.handle_with_subsystem.assert_not_called()

    async def test_opaque_session_ids_do_not_change_pipeline_behavior(self):
        self.pipeline.handle_with_subsystem.return_value = PipelineResult(
            subsystem="exercise_explainer", response="Exercise explanation"
        )
        for session_id in (
            "session-20261014-morning-workout",
            "fcb8d8a0-5a93-4c68-b7b3-e898e2bc3c15",
        ):
            with self.subTest(session_id=session_id):
                self.pipeline.reset_mock()
                status, result = await self.request(
                    "POST", f"/{session_id}/chat",
                    {"query": "Explain squats", "language": "EN"},
                )
                self.assertEqual(status, 200)
                self.assertEqual(result, {
                    "subsystem": "exercise_explainer", "response": "Exercise explanation"
                })
                self.pipeline.handle_with_subsystem.assert_called_once_with(
                    "Explain squats", "EN", session_id=session_id
                )

    async def test_health_endpoint_remains_available(self):
        status, result = await self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(result, {"status": "ok"})
        self.pipeline.handle_with_subsystem.assert_not_called()

    async def test_validation_error_matches_documented_example(self):
        status, result = await self.request(
            "POST", self.chat_path,
            {"query": "Explain a barbell squat.", "language": "French"},
        )
        self.assertEqual(status, 422)
        documented = app.openapi()["paths"]["/{id}/chat"]["post"]["responses"]["422"]
        self.assertEqual(
            result, documented["content"]["application/json"]["example"]
        )
        self.pipeline.handle_with_subsystem.assert_not_called()

    async def test_server_failure_remains_plain_text_and_propagates(self):
        self.pipeline.handle_with_subsystem.side_effect = RuntimeError("Provider unavailable")
        status, result = await self.request(
            "POST", self.chat_path,
            {"query": "Explain a barbell squat.", "language": "EN"},
            expected_error=RuntimeError,
        )
        self.assertEqual(status, 500)
        documented = app.openapi()["paths"]["/{id}/chat"]["post"]["responses"]["500"]
        self.assertEqual(result, documented["content"]["text/plain"]["example"])
        self.pipeline.handle_with_subsystem.assert_called_once_with(
            "Explain a barbell squat.", "EN", session_id=self.session_id
        )

    async def test_documentation_routes_are_available(self):
        status, schema = await self.request("GET", "/openapi.json")
        self.assertEqual(status, 200)
        self.assertEqual(schema, app.openapi())
        for path, marker in (("/docs", "SwaggerUIBundle"), ("/redoc", "redoc")):
            with self.subTest(path=path):
                status, html = await self.request("GET", path)
                self.assertEqual(status, 200)
                self.assertIn(marker, html)
        self.pipeline.handle_with_subsystem.assert_not_called()

    def test_openapi_exposes_both_required_fields_and_response(self):
        schema = app.openapi()
        endpoint = schema["paths"]["/{id}/chat"]["post"]
        self.assertNotIn("/chat", schema["paths"])
        self.assertNotIn("/pipeline", schema["paths"])
        self.assertIn("requestBody", endpoint)
        self.assertIn("200", endpoint["responses"])
        request_schema = schema["components"]["schemas"]["ChatRequest"]
        self.assertIn("ChatResponse", schema["components"]["schemas"])
        self.assertEqual(set(request_schema["required"]), {"query", "language"})
        self.assertEqual(
            request_schema["properties"]["language"]["enum"], ["ES", "EN"]
        )


if __name__ == "__main__":
    unittest.main()
