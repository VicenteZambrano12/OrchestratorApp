import sqlite3
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from api.workout_deps import WorkoutRepository, get_workout_repository
from app import app
import test_chat_endpoint
import test_routine_maker


class WorkoutEndpointTests(unittest.IsolatedAsyncioTestCase):
    request = test_chat_endpoint.ChatEndpointTests.request

    def setUp(self):
        self.fixture = test_routine_maker.RoutineMakerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.routine_id = self.fixture.saved().routine_id
        source = Path(__file__).resolve().parents[2] / "database/gym_app.db"
        with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as db:
            ddl = db.execute(
                "SELECT sql FROM sqlite_master WHERE name = 'fact_workout_sets'"
            ).fetchone()[0]
        with sqlite3.connect(self.fixture.database) as db:
            db.execute(ddl)
            db.execute("INSERT INTO dim_routines (user_id, name) VALUES (2, 'Other user')")
        app.dependency_overrides[get_workout_repository] = lambda: WorkoutRepository(self.fixture.database)
        self.addCleanup(app.dependency_overrides.pop, get_workout_repository)
        self.payload = {
            "routine_id": self.routine_id,
            "sets": [
                {"exercise_id": 1, "reps": 10, "weight": 40, "rpe": 8},
                {"exercise_id": 3, "duration_seconds": 30},
                {"exercise_id": 1, "reps": 8, "weight": 40},
                {"exercise_id": 5, "duration_seconds": 60, "distance_meters": 100},
            ],
        }

    def rows(self):
        with sqlite3.connect(self.fixture.database) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute("SELECT * FROM fact_workout_sets ORDER BY id")]

    async def test_saves_session_with_server_date_and_ordered_sets(self):
        before = self.fixture.rows()
        instant = datetime(2026, 10, 15, 23, 59, 59, tzinfo=timezone.utc)
        with patch("api.workout_deps.datetime") as clock:
            clock.now.return_value = instant
            status, result = await self.request("POST", "/users/1/workouts", self.payload)
            clock.now.assert_called_once_with(timezone.utc)
        self.assertEqual(status, 201)
        self.assertEqual(str(UUID(result["training_id"])), result["training_id"])
        self.assertEqual(result, {
            "training_id": result["training_id"], "user_id": 1,
            "routine_id": self.routine_id, "date": "2026-10-15",
            "created_at": "2026-10-15T23:59:59Z", "sets_saved": 4,
        })
        rows = self.rows()
        self.assertEqual(len(rows), 4)
        for row, item in zip(rows, self.payload["sets"]):
            for field, value in item.items():
                self.assertEqual(row[field], value)
            self.assertEqual(row["user_id"], 1)
            self.assertEqual(row["routine_id"], self.routine_id)
            self.assertEqual(row["training_id"], result["training_id"])
            self.assertEqual(row["created_at"], "2026-10-15 23:59:59")
        self.assertEqual([row["exercise_order"] for row in rows], [1, 2, 1, 3])
        self.assertEqual([row["set_number"] for row in rows], [1, 1, 2, 1])
        self.assertIsNone(rows[1]["reps"])
        self.assertIsNone(rows[1]["weight"])
        self.assertEqual(self.fixture.rows(), before)
        status, other = await self.request("POST", "/users/2/workouts", {
            "routine_id": before[-1][0], "sets": [{"exercise_id": 1, "reps": 1}],
        })
        self.assertEqual(status, 201)
        self.assertNotEqual(other["training_id"], result["training_id"])
        self.assertEqual(self.rows()[-1]["user_id"], 2)

    async def test_each_call_records_a_separate_session(self):
        first = (await self.request("POST", "/users/1/workouts", self.payload))[1]
        second = (await self.request("POST", "/users/1/workouts", self.payload))[1]
        self.assertNotEqual(first["training_id"], second["training_id"])
        self.assertEqual(len(self.rows()), 8)

    async def test_invalid_requests_never_write(self):
        cases = [
            ("/users/999/workouts", self.payload, 404),
            ("/users/0/workouts", self.payload, 422),
            ("/users/abc/workouts", self.payload, 422),
            ("/users/2/workouts", self.payload, 422),
            ("/users/1/workouts", {**self.payload, "routine_id": 999}, 422),
            ("/users/1/workouts", {**self.payload, "routine_id": True}, 422),
            ("/users/1/workouts", {**self.payload, "sets": []}, 422),
            ("/users/1/workouts", {**self.payload, "date": "2000-01-01"}, 422),
            ("/users/1/workouts", {**self.payload, "user_id": 2}, 422),
            ("/users/1/workouts", {}, 422),
        ]
        for field, value in (
            ("exercise_id", 999), ("reps", 0), ("reps", "10"), ("weight", -1),
            ("duration_seconds", 0), ("distance_meters", -1), ("rpe", 11),
            ("rpe", 0), ("unexpected", True),
        ):
            payload = deepcopy(self.payload)
            payload["sets"][-1][field] = value
            cases.append(("/users/1/workouts", payload, 422))
        cases.append(("/users/1/workouts", {
            **self.payload, "sets": [{"exercise_id": 1, "weight": 40}],
        }, 422))
        for url, payload, expected in cases:
            with self.subTest(url=url, payload=payload):
                status, _ = await self.request("POST", url, payload)
                self.assertEqual(status, expected)
                self.assertEqual(self.rows(), [])

    async def test_database_failure_rolls_back_entire_session(self):
        with sqlite3.connect(self.fixture.database) as db:
            db.execute(
                "CREATE TRIGGER reject_second_set BEFORE INSERT ON fact_workout_sets "
                "WHEN NEW.exercise_id = 3 BEGIN SELECT RAISE(ABORT, 'write failed'); END"
            )
        status, _ = await self.request(
            "POST", "/users/1/workouts", self.payload, expected_error=sqlite3.IntegrityError,
        )
        self.assertEqual(status, 500)
        self.assertEqual(self.rows(), [])

    def test_openapi_documents_endpoint_and_server_owned_date(self):
        schema = app.openapi()
        operation = schema["paths"]["/users/{user_id}/workouts"]["post"]
        self.assertIn("201", operation["responses"])
        self.assertEqual(operation["parameters"][0]["name"], "user_id")
        request = schema["components"]["schemas"]["WorkoutRequest"]
        self.assertEqual(set(request["properties"]), {"routine_id", "sets"})
        self.assertFalse(request["additionalProperties"])
