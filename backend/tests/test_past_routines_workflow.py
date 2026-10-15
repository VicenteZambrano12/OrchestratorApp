import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from pydantic import ValidationError

from sql.SQLClient import SQLClient
from systems.past_routines_analyzer.PastRoutinesAnalyzerOrchestrator import (
    PastRoutinesAnalyzerOrchestrator,
)
from systems.past_routines_analyzer.PastRoutinesWorkflow import PastRoutinesWorkflow
from utils.general.GeminiApiCall import GeminiClient
from utils.past_routines_analyzer.dataclass.models import PastRoutinesAnalysis
from utils.past_routines_analyzer.func.load_explainer_prompt import (
    load_explainer_prompt,
)


SCHEMA = Path(__file__).resolve().parents[2] / "database/database_schema.json"
MEMORY = [{
    "user_query": "What did I do on push day?",
    "system_response": "You benched 65 kg.",
    "subsystem_chosen": "past_routines_analyzer",
}]


def route(route_id, day_type=None):
    return json.dumps({"route": route_id, "day_type": day_type})


def build_database(path):
    tables = json.loads(SCHEMA.read_text(encoding="utf-8"))["tables"]
    with closing(sqlite3.connect(path)) as db, db:
        for name in ("dim_users", "dim_exercises", "dim_routines", "fact_workout_sets"):
            db.execute(tables[name]["ddl_sql"])
        db.executemany(
            "INSERT INTO dim_users (id, username) VALUES (?, ?)", [(1, "a"), (2, "b")]
        )
        db.execute(
            "INSERT INTO dim_exercises (id, name, instructions, primary_muscle, pattern, "
            "equipment, mechanic, level, intensity, tracking_type) VALUES (1, "
            "'Bench Press', 'x', 'chest', 'push', 'barbell', 'compound', 'beginner', "
            "'high', 'weight_reps')"
        )
        db.executemany(
            "INSERT INTO dim_routines (id, user_id, name) VALUES (?, ?, ?)",
            [(1, 1, "Push Day A"), (2, 1, "Pull Day A"), (3, 2, "Push Day B")],
        )
        for user, routine, training, weight, days_ago in (
            (1, 1, "push-old", 60.0, 10),
            (1, 1, "push-new", 65.0, 3),
            (1, 2, "pull-new", 50.0, 1),
            (2, 3, "other-user", 99.0, 0),
        ):
            db.execute(
                "INSERT INTO fact_workout_sets (user_id, routine_id, exercise_id, "
                "training_id, reps, weight, rpe, created_at) VALUES "
                "(?, ?, 1, ?, 8, ?, 8.0, DATETIME('now', 'localtime', ?))",
                (user, routine, training, weight, f"-{days_ago} days"),
            )


class PastRoutinesWorkflowTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = Path(directory.name) / "gym.db"
        build_database(self.database)
        self.sql_factory = Mock(
            side_effect=lambda: SQLClient(database_type="sqlite", database_path=self.database)
        )
        self.client = Mock(spec=GeminiClient)
        self.workflow = PastRoutinesWorkflow(
            self.client, sql_client_factory=self.sql_factory
        )

    def explanation_call(self):
        call = self.client.generate.call_args_list[1]
        return json.loads(call.args[0]), call.kwargs

    def test_past_day_flow_returns_route_data_and_explanation(self):
        self.client.generate.side_effect = [route("past_day_exercise", "push"), " Summary \n"]
        result = self.workflow.handle("Show my last push day", user_id=1, language="ES")

        self.assertIsInstance(result, PastRoutinesAnalysis)
        self.assertEqual(
            (result.route, result.day_type, result.llm_explain),
            ("past_day_exercise", "push", "Summary"),
        )
        self.assertEqual(len(result.data), 1)
        row = result.data[0]
        self.assertEqual(
            (row["training_id"], row["training_day"], row["exercise_name"],
             row["reps"], row["weight"], row["weight_unit"], row["rpe"]),
            ("push-new", "Push Day A", "Bench Press", 8, 65.0, "kg", 8.0),
        )
        payload, kwargs = self.explanation_call()
        self.assertEqual(payload, {
            "query": "Show my last push day", "language": "ES",
            "route": "past_day_exercise", "day_type": "push", "data": result.data,
        })
        self.assertEqual(kwargs["system_prompt"], load_explainer_prompt())
        self.assertEqual(kwargs["response_mime_type"], "text/plain")
        self.assertEqual(self.client.generate.call_count, 2)
        self.sql_factory.assert_called_once_with()

    def test_result_serializes_to_json_fields(self):
        self.client.generate.side_effect = [route("past_day_exercise", "pull"), "Pull summary"]
        dumped = json.loads(self.workflow.handle("Pull day?", user_id=1).model_dump_json())
        self.assertEqual(set(dumped), {"route", "day_type", "data", "llm_explain"})
        self.assertEqual(dumped["data"][0]["training_id"], "pull-new")

    def test_compare_flow_returns_last_two_workouts(self):
        self.client.generate.side_effect = [
            route("compare_last_two_workouts", "push"), "Comparison"
        ]
        result = self.workflow.handle("Compare my last two push days", user_id=1)
        self.assertEqual(
            [(r["training_rank"], r["training_id"], r["weight"]) for r in result.data],
            [(1, "push-new", 65.0), (2, "push-old", 60.0)],
        )

    def test_weekly_flow_uses_only_user_scope(self):
        self.client.generate.side_effect = [route("weekly_performance"), "Week"]
        result = self.workflow.handle("How was my week?", user_id=1)
        self.assertEqual(
            [r["training_id"] for r in result.data], ["push-new", "pull-new"]
        )
        self.assertIsNone(self.explanation_call()[0]["day_type"])

    def test_empty_data_is_still_explained(self):
        self.client.generate.side_effect = [route("past_day_exercise", "leg"), "No leg days"]
        result = self.workflow.handle("Show my leg day", user_id=1)
        self.assertEqual((result.data, result.llm_explain), ([], "No leg days"))
        self.assertEqual(self.explanation_call()[0]["data"], [])

    def test_memory_is_passed_to_routing_and_explanation(self):
        self.client.generate.side_effect = [
            route("compare_last_two_workouts", "push"), "Comparison"
        ]
        self.workflow.handle("Compare it with the previous one", user_id=1, memory=MEMORY)
        routing_payload = json.loads(self.client.generate.call_args_list[0].args[0])
        self.assertEqual(routing_payload["memory"], MEMORY)
        self.assertEqual(self.explanation_call()[0]["memory"], MEMORY)

    def test_invalid_input_never_calls_gemini_or_database(self):
        for kwargs in (
            {"user_id": 0}, {"user_id": -1}, {"user_id": True}, {"user_id": "1"},
            {"user_id": None}, {"user_id": 1, "language": "FR"},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.workflow.handle("Show push day", **kwargs)
        with self.assertRaises(ValueError):
            self.workflow.handle(" ", user_id=1)
        self.client.generate.assert_not_called()
        self.sql_factory.assert_not_called()

    def test_failed_routing_never_queries_database(self):
        self.client.generate.return_value = "not json"
        with self.assertRaisesRegex(ValueError, "after 3 attempts"):
            self.workflow.handle("Show push day", user_id=1)
        self.assertEqual(self.client.generate.call_count, 3)
        self.sql_factory.assert_not_called()

    def test_invalid_explanation_is_rejected(self):
        for response in ("", "  ", None):
            with self.subTest(response=response):
                self.client.generate.side_effect = [route("weekly_performance"), response]
                with self.assertRaises(ValueError):
                    self.workflow.handle("My week", user_id=1)

    def test_database_and_provider_errors_propagate(self):
        self.client.generate.side_effect = [route("weekly_performance")]
        self.sql_factory.side_effect = lambda: SQLClient(
            database_type="sqlite", database_path=Path(self.database).with_name("x.db")
        )
        with self.assertRaises(sqlite3.OperationalError):
            self.workflow.handle("My week", user_id=1)

        self.sql_factory.side_effect = None
        self.sql_factory.side_effect = lambda: SQLClient(
            database_type="sqlite", database_path=self.database
        )
        self.client.generate.side_effect = [
            route("weekly_performance"), RuntimeError("Provider unavailable")
        ]
        with self.assertRaisesRegex(RuntimeError, "Provider unavailable"):
            self.workflow.handle("My week", user_id=1)

    def test_default_dependencies(self):
        with patch(
            "systems.past_routines_analyzer.PastRoutinesWorkflow.GeminiClient",
            return_value=self.client,
        ) as factory:
            workflow = PastRoutinesWorkflow()
        factory.assert_called_once_with(max_output_tokens=4096)
        self.assertIsInstance(workflow._orchestrator, PastRoutinesAnalyzerOrchestrator)
        self.assertIs(workflow._orchestrator._client, self.client)
        self.assertIs(workflow._sql_client_factory, SQLClient)

    def test_injected_orchestrator_and_invalid_configuration(self):
        orchestrator = Mock(spec=PastRoutinesAnalyzerOrchestrator)
        orchestrator.route.return_value = Mock(route="weekly_performance", day_type=None)
        self.client.generate.return_value = "Week"
        workflow = PastRoutinesWorkflow(
            self.client, orchestrator=orchestrator, sql_client_factory=self.sql_factory
        )
        self.assertEqual(workflow.handle("Week", user_id=1).llm_explain, "Week")
        orchestrator.route.assert_called_once_with("Week", language="EN", memory=None)

        with self.assertRaises(TypeError):
            PastRoutinesWorkflow(self.client, sql_client_factory="nope")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "explainer.yaml"
            for content in ("[]", "other: x", "explanation: ' '"):
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        PastRoutinesWorkflow(self.client, prompt_path=path)


class PastRoutinesAnalysisModelTests(unittest.TestCase):
    def test_validation(self):
        valid = {"route": "weekly_performance", "data": [], "llm_explain": " ok "}
        self.assertEqual(PastRoutinesAnalysis(**valid).llm_explain, "ok")
        for changes in (
            {"llm_explain": " "}, {"day_type": "push"}, {"data": [{"x": b"raw"}]},
            {"extra": 1}, {"route": "database_direct"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                PastRoutinesAnalysis(**{**valid, **changes})


if __name__ == "__main__":
    unittest.main()
