import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from pydantic import ValidationError

from systems.past_routines_analyzer.PastRoutinesAnalyzerOrchestrator import (
    PastRoutinesAnalyzerOrchestrator,
)
from utils.general.GeminiApiCall import GeminiClient
from utils.past_routines_analyzer.dataclass.models import PastRoutinesRoute
from utils.past_routines_analyzer.func.load_orchestrator_prompts import (
    load_orchestrator_prompts,
)
from utils.past_routines_analyzer.func.load_sql_template import load_sql_template


MEMORY = [{
    "user_query": "What did I do on Monday?",
    "system_response": "On Monday you did squats 3x8 at 60 kg.",
    "subsystem_chosen": "past_routines_analyzer",
}]
SCHEMA = Path(__file__).resolve().parents[2] / "database/database_schema.json"


def answer(route, day_type=None):
    return json.dumps({"route": route, "day_type": day_type})


class PastRoutinesAnalyzerOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock(spec=GeminiClient)
        self.orchestrator = PastRoutinesAnalyzerOrchestrator(self.client)

    def payload(self, call_index=0):
        return json.loads(self.client.generate.call_args_list[call_index].args[0])

    def test_returns_validated_route_and_day_type(self):
        for response, expected in (
            (answer("past_day_exercise", "push"), ("past_day_exercise", "push")),
            (answer("compare_last_two_workouts", " Leg "), ("compare_last_two_workouts", "leg")),
            (answer("past_day_exercise"), ("past_day_exercise", None)),
            (answer("weekly_performance"), ("weekly_performance", None)),
            (f"\n{answer('compare_last_two_workouts', 'full body')} ",
             ("compare_last_two_workouts", "full body")),
        ):
            with self.subTest(response=response):
                self.client.reset_mock()
                self.client.generate.return_value = response
                decision = self.orchestrator.route("Some history request")
                self.assertIsInstance(decision, PastRoutinesRoute)
                self.assertEqual((decision.route, decision.day_type), expected)
                self.client.generate.assert_called_once()

    def test_sends_query_routes_language_and_json_mode(self):
        self.client.generate.return_value = answer("weekly_performance")
        self.orchestrator.route("¿Cómo rendí la última semana?", language="ES")
        payload = self.payload()
        self.assertEqual(payload["query"], "¿Cómo rendí la última semana?")
        self.assertEqual(payload["language"], "ES")
        self.assertEqual(
            [r["id"] for r in payload["routes"]],
            list(PastRoutinesAnalyzerOrchestrator.ROUTES),
        )
        self.assertNotIn("memory", payload)
        kwargs = self.client.generate.call_args.kwargs
        self.assertIn("Past Routines Orchestrator", kwargs["system_prompt"])
        self.assertIn("day_type", kwargs["system_prompt"])
        self.assertEqual(kwargs["response_mime_type"], "application/json")

    def test_memory_is_sent_as_context(self):
        self.client.generate.return_value = answer("compare_last_two_workouts", "push")
        decision = self.orchestrator.route("Compare it with the previous one", memory=MEMORY)
        self.assertEqual(decision.day_type, "push")
        self.assertEqual(self.payload()["memory"], MEMORY)

    def test_invalid_answers_are_retried(self):
        self.client.generate.side_effect = [
            "past_day_exercise",
            answer("weekly_performance", "push"),
            answer("past_day_exercise", "pull"),
        ]
        decision = self.orchestrator.route("Show pull day")
        self.assertEqual((decision.route, decision.day_type), ("past_day_exercise", "pull"))
        self.assertEqual(self.client.generate.call_count, 3)

    def test_three_invalid_answers_raise(self):
        for bad in (
            "not json", "[]", "{}", None,
            answer("database_direct"),
            answer("no_system"),
            answer("weekly_performance", "leg"),
            answer("past_day_exercise", "50%_push"),
            answer("past_day_exercise", "2026-10-08"),
            answer("past_day_exercise", ""),
            answer("past_day_exercise", "x" * 41),
            '{"route": "past_day_exercise", "day_type": 3}',
            '{"route": "past_day_exercise", "day_type": null, "extra": 1}',
        ):
            with self.subTest(bad=bad):
                self.client.reset_mock()
                self.client.generate.side_effect = None
                self.client.generate.return_value = bad
                with self.assertRaisesRegex(ValueError, "after 3 attempts"):
                    self.orchestrator.route("Show my workouts")
                self.assertEqual(self.client.generate.call_count, 3)

    def test_route_restricted_by_prompt_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "orchestrator.yaml"
            path.write_text(
                "system_prompt: x\nuser_prompt: '{payload}'\n"
                "routes: {weekly_performance: Weekly review}",
                encoding="utf-8",
            )
            orchestrator = PastRoutinesAnalyzerOrchestrator(self.client, path)
            self.client.generate.return_value = answer("past_day_exercise", "push")
            with self.assertRaisesRegex(ValueError, "after 3 attempts"):
                orchestrator.route("Show push day")

    def test_invalid_input_never_calls_gemini(self):
        for query, language, memory in (
            ("", "EN", None), (None, "EN", None), ("Show Monday", "FR", None),
            ("Show Monday", "EN", [{"user_query": "x"}]),
        ):
            with self.subTest(query=query, language=language, memory=memory):
                with self.assertRaises(ValueError):
                    self.orchestrator.route(query, language=language, memory=memory)
        self.client.generate.assert_not_called()

    def test_provider_errors_propagate(self):
        self.client.generate.side_effect = RuntimeError("Provider unavailable")
        with self.assertRaisesRegex(RuntimeError, "Provider unavailable"):
            self.orchestrator.route("Show Monday")

    def test_default_client_is_created(self):
        with patch(
            "systems.past_routines_analyzer.PastRoutinesAnalyzerOrchestrator.GeminiClient",
            return_value=self.client,
        ) as factory:
            PastRoutinesAnalyzerOrchestrator()
        factory.assert_called_once_with()

    def test_default_prompt_routes_match_class_routes(self):
        self.assertEqual(
            tuple(load_orchestrator_prompts()["routes"]),
            PastRoutinesAnalyzerOrchestrator.ROUTES,
        )

    def test_invalid_prompt_configuration_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "orchestrator.yaml"
            for content in (
                "[]",
                "system_prompt: x\nuser_prompt: '{payload}'",
                "system_prompt: x\nuser_prompt: nope\nroutes: {a: b}",
                "system_prompt: ''\nuser_prompt: '{payload}'\nroutes: {a: b}",
                "system_prompt: x\nuser_prompt: '{payload}'\nroutes: {a: ''}",
            ):
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        PastRoutinesAnalyzerOrchestrator(self.client, path)


class PastRoutinesRouteModelTests(unittest.TestCase):
    def test_day_type_is_normalized_and_validated(self):
        self.assertEqual(
            PastRoutinesRoute(route="past_day_exercise", day_type="  Full   BODY ").day_type,
            "full body",
        )
        for day_type in ("", "%", "push_day", "día", "1push", "a" * 41):
            with self.subTest(day_type=day_type), self.assertRaises(ValidationError):
                PastRoutinesRoute(route="past_day_exercise", day_type=day_type)

    def test_weekly_performance_rejects_day_type(self):
        self.assertIsNone(PastRoutinesRoute(route="weekly_performance").day_type)
        with self.assertRaises(ValidationError):
            PastRoutinesRoute(route="weekly_performance", day_type="push")


class PastRoutinesSqlTemplateTests(unittest.TestCase):
    """Run each template against an in-memory copy of the real schema."""

    def setUp(self):
        tables = json.loads(SCHEMA.read_text(encoding="utf-8"))["tables"]
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        for name in ("dim_users", "dim_exercises", "dim_routines", "fact_workout_sets"):
            self.db.execute(tables[name]["ddl_sql"])
        self.db.executemany(
            "INSERT INTO dim_users (id, username) VALUES (?, ?)", [(1, "a"), (2, "b")]
        )
        self.db.executemany(
            "INSERT INTO dim_exercises (id, name, instructions, primary_muscle, pattern, "
            "equipment, mechanic, level, intensity, tracking_type) "
            "SELECT ?, ?, 'x', ?, pattern, equipment, mechanic, level, intensity, "
            "tracking_type FROM (SELECT 'push' AS pattern, 'barbell' AS equipment, "
            "'compound' AS mechanic, 'beginner' AS level, 'high' AS intensity, "
            "'weight_reps' AS tracking_type)",
            [(1, "Bench Press", "chest"), (2, "Barbell Row", "back")],
        )
        self.db.executemany(
            "INSERT INTO dim_routines (id, user_id, name) VALUES (?, ?, ?)",
            [(1, 1, "Push Day A (Chest/Triceps/Delts)"), (2, 1, "Pull Day A (Back/Biceps)"),
             (3, 2, "Push Day B")],
        )
        # (user, routine, exercise, training_id, set_number, weight, days_ago)
        for row in (
            (1, 1, 1, "push-old", 1, 60.0, 20),
            (1, 1, 1, "push-mid", 1, 62.5, 10),
            (1, 1, 1, "push-new", 1, 65.0, 3),
            (1, 1, 1, "push-new", 2, 65.0, 3),
            (1, 2, 2, "pull-new", 1, 50.0, 1),
            (1, 1, 1, None, 1, 40.0, 0),
            (2, 3, 1, "other-user", 1, 99.0, 0),
        ):
            self.db.execute(
                "INSERT INTO fact_workout_sets (user_id, routine_id, exercise_id, "
                "training_id, set_number, reps, weight, created_at) VALUES "
                "(?, ?, ?, ?, ?, 8, ?, DATETIME('now', 'localtime', ?))",
                (*row[:6], f"-{row[6]} days"),
            )

    def tearDown(self):
        self.db.close()

    def run_template(self, route, **params):
        return [dict(r) for r in self.db.execute(load_sql_template(route), params)]

    def test_past_day_returns_latest_fuzzy_matching_training(self):
        rows = self.run_template("past_day_exercise", user_id=1, day_type="PUSH")
        self.assertEqual({r["training_id"] for r in rows}, {"push-new"})
        self.assertEqual([r["set_number"] for r in rows], [1, 2])
        self.assertEqual(rows[0]["exercise_name"], "Bench Press")
        self.assertEqual(rows[0]["weight_unit"], "kg")
        self.assertEqual(
            self.run_template("past_day_exercise", user_id=1, day_type="back")[0]["training_id"],
            "pull-new",
        )
        self.assertEqual(self.run_template("past_day_exercise", user_id=1, day_type="leg"), [])

    def test_past_day_with_null_day_type_returns_latest_any_day(self):
        rows = self.run_template("past_day_exercise", user_id=1, day_type=None)
        self.assertEqual({r["training_id"] for r in rows}, {"pull-new"})

    def test_compare_returns_last_two_trainings_ranked(self):
        rows = self.run_template("compare_last_two_workouts", user_id=1, day_type="push")
        self.assertEqual(
            [(r["training_rank"], r["training_id"], r["weight"]) for r in rows],
            [(1, "push-new", 65.0), (1, "push-new", 65.0), (2, "push-mid", 62.5)],
        )
        rows = self.run_template("compare_last_two_workouts", user_id=1, day_type=None)
        self.assertEqual(
            sorted({(r["training_rank"], r["training_id"]) for r in rows}),
            [(1, "pull-new"), (2, "push-new")],
        )

    def test_weekly_returns_logged_trainings_of_last_seven_days(self):
        rows = self.run_template("weekly_performance", user_id=1)
        self.assertEqual(
            [r["training_id"] for r in rows], ["push-new", "push-new", "pull-new"]
        )
        self.assertEqual(self.run_template("weekly_performance", user_id=2)[0]["weight"], 99.0)

    def test_unknown_route_template_is_rejected(self):
        with self.assertRaises(ValueError):
            load_sql_template("database_direct")


if __name__ == "__main__":
    unittest.main()
