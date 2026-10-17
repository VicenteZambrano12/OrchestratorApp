import sqlite3
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app import app
import test_workouts_endpoint


class GetUserDaysEndpointTests(unittest.IsolatedAsyncioTestCase):
    request = test_workouts_endpoint.WorkoutEndpointTests.request

    def setUp(self):
        self.fixture = test_workouts_endpoint.WorkoutEndpointTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.clock = self.enterContext(patch("api.workout_deps.datetime"))
        self.clock.now.return_value = datetime(2026, 10, 15, tzinfo=timezone.utc)

    def seed(self, timestamp, *, user_id=1, training_id="session"):
        routine_id = (
            self.fixture.routine_id if user_id == 1 else self.fixture.fixture.rows()[-1][0]
        )
        with sqlite3.connect(self.fixture.fixture.database) as db:
            db.execute(
                "INSERT INTO fact_workout_sets "
                "(user_id, routine_id, exercise_id, training_id, reps, created_at) "
                "VALUES (?, ?, 1, ?, 10, ?)",
                (user_id, routine_id, training_id, timestamp),
            )

    async def test_returns_exact_seven_day_shape_with_logged_workouts_only(self):
        for timestamp in (
            "2026-10-08 23:59:59",
            "2026-10-09 00:00:00",
            "2026-10-12 10:00:00",
            "2026-10-12 10:00:00",
            "2026-10-15 23:59:59",
            "2026-10-16 00:00:00",
        ):
            self.seed(timestamp)
        self.seed("2026-10-12 18:00:00", training_id="another-session")
        self.seed("2026-10-10 12:00:00", training_id=None)
        self.seed("2026-10-11 12:00:00", user_id=2)
        before = self.fixture.rows()

        status, result = await self.request("GET", "/users/1/days")

        self.assertEqual(status, 200)
        self.assertEqual(result, [
            {"date": "2026-10-09", "day_of_week": "Friday", "has_routine": True},
            {"date": "2026-10-10", "day_of_week": "Saturday", "has_routine": False},
            {"date": "2026-10-11", "day_of_week": "Sunday", "has_routine": False},
            {"date": "2026-10-12", "day_of_week": "Monday", "has_routine": True},
            {"date": "2026-10-13", "day_of_week": "Tuesday", "has_routine": False},
            {"date": "2026-10-14", "day_of_week": "Wednesday", "has_routine": False},
            {"date": "2026-10-15", "day_of_week": "Thursday", "has_routine": True},
        ])
        self.assertEqual(self.fixture.rows(), before)
        self.clock.now.assert_called_once_with(timezone.utc)

    async def test_no_routines_or_workouts_returns_seven_false_flags(self):
        with sqlite3.connect(self.fixture.fixture.database) as db:
            db.execute("DELETE FROM dim_routines WHERE user_id = 2")
        status, result = await self.request("GET", "/users/2/days")
        self.assertEqual(status, 200)
        self.assertEqual(len(result), 7)
        self.assertTrue(all(item["has_routine"] is False for item in result))

    async def test_window_crosses_year_and_leap_day_boundaries(self):
        for today, first, last in (
            (datetime(2027, 1, 3, tzinfo=timezone.utc), "2026-12-28", "2027-01-03"),
            (datetime(2028, 3, 2, tzinfo=timezone.utc), "2028-02-25", "2028-03-02"),
        ):
            with self.subTest(today=today):
                self.clock.now.return_value = today
                status, result = await self.request("GET", "/users/1/days")
                self.assertEqual(status, 200)
                self.assertEqual(len(result), 7)
                self.assertEqual(result[0]["date"], first)
                self.assertEqual(result[-1]["date"], last)
                self.assertEqual(result[-1]["day_of_week"], today.strftime("%A"))
                if today.year == 2028:
                    self.assertIn("2028-02-29", [item["date"] for item in result])

    async def test_rejects_unknown_and_invalid_users(self):
        for user_id, expected in (("999", 404), ("0", 422), ("-1", 422), ("abc", 422)):
            with self.subTest(user_id=user_id):
                status, body = await self.request("GET", f"/users/{user_id}/days")
                self.assertEqual(status, expected)
                self.assertIn("detail", body)

    async def test_database_errors_are_not_reported_as_empty_activity(self):
        with sqlite3.connect(self.fixture.fixture.database) as db:
            db.execute("DROP TABLE fact_workout_sets")
        status, _ = await self.request(
            "GET", "/users/1/days", expected_error=sqlite3.OperationalError,
        )
        self.assertEqual(status, 500)

    def test_openapi_documents_path_and_list_response(self):
        operation = app.openapi()["paths"]["/users/{user_id}/days"]["get"]
        self.assertEqual(operation["parameters"][0]["name"], "user_id")
        self.assertEqual(operation["parameters"][0]["in"], "path")
        self.assertTrue(operation["parameters"][0]["required"])
        self.assertIn("404", operation["responses"])
        self.assertIn("422", operation["responses"])
        schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
        self.assertEqual(schema["type"], "array")
        self.assertEqual(schema["items"], {"$ref": "#/components/schemas/WorkoutDay"})
