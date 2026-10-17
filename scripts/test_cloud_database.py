# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = [
#   "psycopg[binary]>=3.2,<4", "pgserver>=0.1.4,<1",
#   "fastapi>=0.115,<1", "python-dotenv>=1,<2",
# ]
# ///
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pgserver
import psycopg
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend/src"))

from api.DataClasses.Workout import WorkoutRequest
from api.user_deps import UserRegistration, UserRepository
from api.workout_deps import WorkoutRepository
from sql.SQLClient import SQLClient
from utils.exercise_explainer.func.catalog import ExerciseCatalog
from utils.past_routines_analyzer.dataclass.models import PastRoutinesRoute
from utils.past_routines_analyzer.func.fetch_history import fetch_history
from utils.pipeline.progress import progress_listener
from utils.routinemaker.dataclass.models import (
    ROUTINE_PLAN_EXAMPLE, RoutineParameters, RoutinePlan,
)
from utils.routinemaker.func.repository import RoutineDataError, RoutineRepository
from migrate_database import TABLES


SQL_MODULE = importlib.import_module("sql.SQLClient")
CLOUD_URL = "postgresql://demo:private-test-password@invalid.example/app?sslmode=require"


class CloudDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cluster = tempfile.TemporaryDirectory(prefix="orchestrator-cloud-test-")
        cls.server = pgserver.get_server(Path(cls.cluster.name) / "pgdata", cleanup_mode="stop")
        cls.uri = cls.server.get_uri()

    @classmethod
    def tearDownClass(cls):
        cls.server.cleanup()
        cls.cluster.cleanup()

    def setUp(self):
        self.admin = psycopg.connect(self.uri, autocommit=True)
        self.addCleanup(self.admin.close)
        self.admin.execute("DROP SCHEMA public CASCADE")
        self.admin.execute("CREATE SCHEMA public")
        for statement in TABLES.values():
            self.admin.execute(statement)
        self.admin.execute(
            "INSERT INTO dim_exercises "
            "(name, instructions, primary_muscle, pattern, equipment, mechanic, level, intensity, media_url) "
            "VALUES ('Barbell Bench Press', 'Press carefully.', 'chest', 'push', 'barbell', "
            "'compound', 'beginner', 'medium', '[\"images/press/0.jpg\", \"images/press/1.jpg\"]')"
        )
        self.parameters = RoutineParameters(
            routine_type="ppl", days_per_week=1, hours_per_session=1.0, level="beginner",
        )
        self.plan = RoutinePlan.model_validate(ROUTINE_PLAN_EXAMPLE)
        env = patch.dict(os.environ, {"MODE": "CLOUD", "DATABASE_URL": CLOUD_URL}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(patch.stopall)
        patch.object(SQL_MODULE, "ENV_FILE", Path(self.cluster.name) / "absent.env").start()
        patch.object(
            SQL_MODULE, "_connect_sqlite",
            side_effect=AssertionError("Cloud repositories must never connect to SQLite."),
        ).start()
        connect = psycopg.connect

        def connect_locally(uri, **kwargs):
            self.assertEqual(uri, CLOUD_URL)
            self.assertIsNone(kwargs["prepare_threshold"])
            # Only redirect the connection destination; queries use real PostgreSQL.
            return connect(self.uri, **kwargs)

        patch.object(SQL_MODULE.psycopg, "connect", side_effect=connect_locally).start()

    def user(self, name="Cloud user"):
        return UserRepository().create(UserRegistration(username=name, weight_unit="kg"))

    def routine(self, user_id, draft_id="draft"):
        return RoutineRepository().save(user_id, self.plan, self.parameters, draft_id, None)

    def workout(self, routine_id):
        return WorkoutRequest.model_validate({
            "routine_id": routine_id,
            "sets": [
                {"exercise_id": 1, "reps": 8, "weight": 30.0},
                {"exercise_id": 1, "reps": 10, "weight": 30.0},
            ],
        })

    def test_cloud_binding_dates_and_progress_keep_the_existing_shapes(self):
        events = []
        with progress_listener(events.append), SQLClient() as db:
            db.begin_write()
            db.execute("CREATE TABLE items (name TEXT UNIQUE)")
            db.execute("INSERT INTO items VALUES (?)", ("private-value",))
            db.executemany("INSERT INTO items VALUES (:name)", [{"name": "second"}, {"name": "third"}])
            self.assertEqual(
                db.fetch_one(
                    "SELECT name, '100% ? :literal' AS literal FROM items "
                    "WHERE name LIKE '%' || :name || '%' -- ignored :comment ?",
                    {"name": "private"},
                ),
                {"name": "private-value", "literal": "100% ? :literal"},
            )
            self.assertEqual(db.fetch_one("SELECT '100%' AS literal"), {"literal": "100%"})
            self.assertEqual(
                db.fetch_one("SELECT DATE('2026-01-02') AS day"), {"day": "2026-01-02"},
            )
            self.assertIsNone(db.fetch_one("SELECT name FROM items WHERE name = ?", ("absent",)))
            self.assertEqual(len(db.fetch_all("SELECT * FROM items")), 3)
        self.assertTrue(all(event["source"] == "PostgreSQL / app" for event in events))
        self.assertNotIn("private-test-password", json.dumps(events))
        self.assertNotIn("private-value", json.dumps(events))

    def test_failed_writes_roll_back_and_connections_close(self):
        db = SQLClient()
        with self.assertRaisesRegex(RuntimeError, "discard"):
            with db:
                db.execute("INSERT INTO dim_users (username) VALUES (?)", ("discard",))
                raise RuntimeError("discard")
        self.assertEqual(self.admin.execute("SELECT COUNT(*) FROM dim_users").fetchone()[0], 0)
        with self.assertRaisesRegex(RuntimeError, "not connected"):
            db.fetch_all("SELECT 1")
        with self.assertRaises(psycopg.errors.UniqueViolation), db:
            db.executemany(
                "INSERT INTO dim_users (username) VALUES (?)", [("duplicate",), ("duplicate",)],
            )
        self.assertEqual(self.admin.execute("SELECT COUNT(*) FROM dim_users").fetchone()[0], 0)

    def test_users_seed_once_and_duplicate_registration_returns_conflict(self):
        repository = UserRepository()
        seeded = repository.list_users()
        self.assertEqual(len(seeded), 1)
        self.assertEqual(repository.list_users(), seeded)
        user = self.user()
        self.assertEqual(repository.list_users()[-1], user)
        with self.assertRaises(HTTPException) as raised:
            self.user()
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(len(repository.list_users()), 2)

    def test_exercise_catalog_and_routine_lifecycle_use_cloud_data(self):
        exercises, missing = ExerciseCatalog().resolve(["barbell bench press"])
        self.assertEqual(missing, [])
        self.assertEqual(exercises[0]["media_urls"], ["images/press/0.jpg", "images/press/1.jpg"])
        user = self.user()
        repository = RoutineRepository()
        self.assertEqual(repository.catalog(self.parameters)[0]["id"], 1)
        first = self.routine(user.id)
        self.assertEqual(self.routine(user.id), first)
        self.assertEqual(repository.load(user.id, first), (self.plan, self.parameters))
        self.assertEqual(repository.active_routine_record(user.id), (first, self.plan))
        second = self.routine(user.id, "new-draft")
        self.assertNotEqual(first, second)
        self.assertEqual(repository.active_routine_record(user.id), (second, self.plan))
        self.assertEqual(len(repository.routines(user.id)), 2)
        other = self.user("Second user")
        self.assertNotEqual(self.routine(other.id), first)
        with self.assertRaises(ValueError):
            repository.load(other.id, first)

    def test_concurrent_saves_remain_idempotent(self):
        user = self.user()
        with ThreadPoolExecutor(max_workers=2) as executor:
            identifiers = list(executor.map(lambda _: self.routine(user.id), range(2)))
        self.assertEqual(identifiers[0], identifiers[1])
        self.assertEqual(
            self.admin.execute("SELECT COUNT(*) FROM dim_routines WHERE is_active = 1").fetchone()[0], 1,
        )

    def test_legacy_routines_and_malformed_json_are_handled_without_sql_json_functions(self):
        user = self.user()
        for description in ("42", "Legacy plain text", "{broken JSON"):
            self.admin.execute(
                "INSERT INTO dim_routines (user_id, name, description) VALUES (%s, 'Push', %s)",
                (user.id, description),
            )
        self.admin.execute(
            "INSERT INTO fact_workout_sets (user_id, routine_id, exercise_id, reps) "
            "VALUES (%s, 1, 1, 8), (%s, 2, 1, 8), (%s, 3, 1, 8)",
            (user.id, user.id, user.id),
        )
        repository = RoutineRepository()
        with self.assertRaises(RoutineDataError):
            repository.active_routine_record(user.id)
        self.admin.execute("UPDATE dim_routines SET is_active = 0 WHERE id = 3")
        identifier, legacy = repository.active_routine_record(user.id)
        self.assertEqual(identifier, 2)
        self.assertEqual([day.routine_id for day in legacy.days], [2])
        self.assertGreater(self.routine(user.id), 3)

    def test_workouts_dates_and_partial_failure_rollback(self):
        user = self.user()
        routine_id = self.routine(user.id)
        repository = WorkoutRepository()
        result = repository.save(user.id, self.workout(routine_id))
        self.assertEqual(result.sets_saved, 2)
        days = repository.days(user.id)
        self.assertEqual(len(days), 7)
        self.assertTrue(days[-1].has_routine)
        self.assertEqual(sum(day.has_routine for day in days), 1)
        self.assertEqual(
            self.admin.execute("SELECT exercise_order, set_number FROM fact_workout_sets ORDER BY id").fetchall(),
            [(1, 1), (1, 2)],
        )
        self.admin.execute("DELETE FROM fact_workout_sets")
        self.admin.execute("ALTER TABLE fact_workout_sets ADD CONSTRAINT test_reps CHECK (reps < 10)")
        with self.assertRaises(psycopg.errors.CheckViolation):
            repository.save(user.id, self.workout(routine_id))
        self.assertEqual(self.admin.execute("SELECT COUNT(*) FROM fact_workout_sets").fetchone()[0], 0)
        with self.assertRaises(HTTPException) as raised:
            repository.save(self.user("Other user").id, self.workout(routine_id))
        self.assertEqual(raised.exception.status_code, 422)

    def test_all_history_routes_execute_with_nullable_filters_and_user_scoping(self):
        user = self.user()
        other = self.user("Other user")
        routine_id = self.routine(user.id)
        other_routine = self.routine(other.id)
        now = datetime.now(timezone.utc).replace(microsecond=0)
        for offset, training_id in ((8, "old"), (6, "boundary"), (1, "yesterday"), (0, "latest")):
            self.admin.execute(
                "INSERT INTO fact_workout_sets "
                "(user_id, routine_id, exercise_id, training_id, reps, created_at) "
                "VALUES (%s, %s, 1, %s, 8, %s)",
                (user.id, routine_id, training_id, (now - timedelta(days=offset)).strftime("%Y-%m-%d %H:%M:%S")),
            )
        self.admin.execute(
            "INSERT INTO fact_workout_sets "
            "(user_id, routine_id, exercise_id, training_id, reps, created_at) "
            "VALUES (%s, %s, 1, 'other-user', 8, %s)",
            (other.id, other_routine, now.strftime("%Y-%m-%d %H:%M:%S")),
        )
        for route, expected in (
            ("past_day_exercise", {"latest"}),
            ("compare_last_two_workouts", {"latest", "yesterday"}),
            ("weekly_performance", {"boundary", "yesterday", "latest"}),
        ):
            for day_type in (None, "push") if route != "weekly_performance" else (None,):
                with self.subTest(route=route, day_type=day_type):
                    rows = fetch_history(
                        SQLClient, PastRoutinesRoute(route=route, day_type=day_type), user.id,
                    )
                    self.assertEqual({row["training_id"] for row in rows}, expected)
                    self.assertTrue(all(isinstance(row["training_date"], str) for row in rows))
                    json.dumps(rows)
        self.assertEqual(
            fetch_history(SQLClient, PastRoutinesRoute(route="past_day_exercise", day_type="pull"), user.id),
            [],
        )


if __name__ == "__main__":
    unittest.main()
