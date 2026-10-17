import json
import sqlite3
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

from api.Endpoint.active_routine import get_routine_repository
from api.Endpoint.chat import get_pipeline
from api.redis_deps import GetNTurns, SetTurn, get_routine_store, get_set_turn
from app import app
from systems.orch.Orchestrator import Orchestrator
from systems.pipeline.Pipeline import Pipeline
import test_chat_endpoint
import test_routine_maker


class SetRoutineEndpointTests(unittest.IsolatedAsyncioTestCase):
    request = test_chat_endpoint.ChatEndpointTests.request

    def setUp(self):
        self.fixture = test_routine_maker.RoutineMakerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.repository = self.fixture.maker._repository
        app.dependency_overrides[get_routine_repository] = lambda: self.repository
        self.addCleanup(app.dependency_overrides.pop, get_routine_repository)
        for dependency, override in (
            (get_routine_store, lambda: self.fixture.store),
            (get_set_turn, lambda: SetTurn(self.fixture.store)),
        ):
            app.dependency_overrides[dependency] = override
            self.addCleanup(app.dependency_overrides.pop, dependency)

    def draft_url(self, draft_id, user_id=1, session_id="session"):
        return (
            f"/users/{user_id}/routine?session_id={session_id}"
            f"&draft_id={draft_id}&language=EN"
        )

    async def test_button_put_saves_cached_preview_once_and_updates_memory(self):
        preview = self.fixture.draft()
        payload = preview.routine.model_dump(mode="json")
        url = self.draft_url(preview.draft_id)
        for _ in range(2):
            self.assertEqual(await self.request("PUT", url, payload), (200, payload))
        self.assertEqual(len(self.fixture.rows()), 1)
        self.assertFalse(self.fixture.state().awaiting_confirmation)
        self.assertEqual(self.fixture.state().saved_routine_id, self.fixture.rows()[0][0])
        _, parameters = self.repository.load(1, self.fixture.rows()[0][0])
        self.assertEqual(parameters.model_dump(), test_routine_maker.COMPLETE)
        turns = GetNTurns(self.fixture.store).get("session", 2)
        self.assertEqual(list(turns.values())[-1]["routine"], payload)
        self.assertEqual(self.fixture.client.generate.call_count, 2)

    async def test_chat_confirmation_defers_write_until_put(self):
        preview = self.fixture.draft()
        orchestrator = Mock(spec=Orchestrator)
        orchestrator.route.return_value = "routine_maker"
        pipeline = Pipeline(
            orchestrator, routine_maker=self.fixture.maker,
            turn_setter=SetTurn(self.fixture.store),
            turn_getter=GetNTurns(self.fixture.store),
        )
        app.dependency_overrides[get_pipeline] = lambda: pipeline
        self.addCleanup(app.dependency_overrides.pop, get_pipeline)
        self.fixture.client.generate.side_effect = [test_routine_maker.decision("save")]
        status, result = await self.request("POST", "/session/chat", {
            "query": "Yes, save it", "language": "EN", "user_id": 1,
            "client_saves_routine": True,
        })
        self.assertEqual(status, 200)
        self.assertEqual(result["response"]["status"], "save_requested")
        self.assertEqual(result["response"]["draft_id"], preview.draft_id)
        self.assertEqual(self.fixture.rows(), [])
        self.assertTrue(self.fixture.state().awaiting_confirmation)
        payload = result["response"]["routine"]
        self.assertEqual(
            await self.request("PUT", self.draft_url(preview.draft_id), payload),
            (200, payload),
        )
        self.assertEqual(len(self.fixture.rows()), 1)
        self.assertFalse(self.fixture.state().awaiting_confirmation)

    async def test_draft_put_rejects_stale_changed_and_other_scope_without_writes(self):
        preview = self.fixture.draft()
        payload = preview.routine.model_dump(mode="json")
        changed = deepcopy(payload)
        changed["name"] = "Not the preview"
        for url, body in (
            (self.draft_url("stale"), payload),
            (self.draft_url(preview.draft_id, user_id=2), payload),
            (self.draft_url(preview.draft_id, session_id="other"), payload),
            (self.draft_url(preview.draft_id), changed),
            ("/users/1/routine?session_id=session", payload),
            (f"/users/1/routine?draft_id={preview.draft_id}", payload),
        ):
            with self.subTest(url=url, body=body):
                status, _ = await self.request("PUT", url, body)
                self.assertEqual(status, 422)
                self.assertEqual(self.fixture.rows(), [])
                self.assertTrue(self.fixture.state().awaiting_confirmation)

    async def test_draft_retry_does_not_reactivate_older_routine(self):
        preview = self.fixture.draft()
        payload = preview.routine.model_dump(mode="json")
        url = self.draft_url(preview.draft_id)
        await self.request("PUT", url, payload)
        updated = deepcopy(payload)
        updated["name"] = "New current routine"
        await self.request("PUT", "/users/1/routine", updated)
        before = self.fixture.rows()
        await self.request("PUT", url, payload)
        self.assertEqual(self.fixture.rows(), before)
        self.assertEqual(await self.request("GET", "/users/1/routine"), (200, updated))

    async def test_sets_first_routine_and_get_returns_saved_plan(self):
        payload = test_routine_maker.plan()
        status, saved = await self.request("PUT", "/users/1/routine", payload)
        self.assertEqual(status, 200)
        expected = deepcopy(payload)
        for day, name in zip(expected["days"], ("Bench Press", "Pulldown", "Squat")):
            day["exercises"][0]["name"] = name
        self.assertEqual(saved, expected)
        self.assertEqual(await self.request("GET", "/users/1/routine"), (200, saved))
        rows = self.fixture.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], 1)
        self.assertEqual(rows[0][4], 1)
        stored, parameters = self.repository.load(1, rows[0][0])
        self.assertEqual(stored.model_dump(mode="json"), saved)
        self.assertEqual(parameters.days_per_week, 3)
        self.assertEqual(parameters.hours_per_session, 0.75)

    async def test_routine_headers_identify_the_exact_loaded_and_saved_versions(self):
        status, result, headers = await self.request(
            "GET", "/users/1/routine", include_headers=True,
        )
        self.assertEqual((status, result), (200, None))
        self.assertNotIn(b"x-routine-id", headers)
        for name in ("First version", "Second version"):
            payload = test_routine_maker.plan()
            payload["name"] = name
            status, saved, headers = await self.request(
                "PUT", "/users/1/routine", payload, include_headers=True,
            )
            self.assertEqual(status, 200)
            routine_id = int(headers[b"x-routine-id"])
            self.assertEqual(routine_id, self.fixture.rows()[-1][0])
            status, loaded, get_headers = await self.request(
                "GET", "/users/1/routine", include_headers=True,
            )
            self.assertEqual((status, loaded), (200, saved))
            self.assertEqual(int(get_headers[b"x-routine-id"]), routine_id)

    async def test_get_active_routine_reports_invalid_json_plan_without_server_error(self):
        saved = self.fixture.saved()
        with sqlite3.connect(self.fixture.database) as db:
            db.execute(
                "UPDATE dim_routines SET description = ? WHERE id = ?",
                ('{"routine": {}}', saved.routine_id),
            )

        status, body = await self.request("GET", "/users/1/routine")

        self.assertEqual(status, 409)
        self.assertIn("legacy or invalid data", body["detail"])

    def seed_legacy_templates(self):
        source = Path(__file__).resolve().parents[2] / "database/gym_app.db"
        with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as db:
            ddl = db.execute(
                "SELECT sql FROM sqlite_master WHERE name = 'fact_workout_sets'"
            ).fetchone()[0]
        with sqlite3.connect(self.fixture.database) as db:
            db.execute(ddl)
            db.executemany(
                "INSERT INTO dim_routines(id, user_id, name, description, is_active) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (9, 2, "Push", "Pressing exercises.", 1),
                    (10, 2, "Pull", "Pulling exercises.", 1),
                    (11, 2, "Legs", "Leg exercises.", 1),
                    (12, 2, "Empty draft", "Not yet populated.", 1),
                    (13, 2, "Old template", "Inactive.", 0),
                    (14, 1, "Other user", "Not user two.", 1),
                ],
            )
            db.executemany(
                "INSERT INTO fact_workout_sets "
                "(user_id, routine_id, exercise_id, training_id, exercise_order, "
                "set_number, reps, weight, duration_seconds) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (2, 9, 1, None, 1, 1, 8, 70, None),
                    (2, 9, 1, None, 1, 2, 6, 75, None),
                    (2, 10, 5, None, 1, 1, 10, None, 60),
                    (2, 11, 3, None, 1, 1, 12, 90, None),
                    (2, 12, 1, "historical-only", 1, 1, 10, 50, None),
                    (2, 13, 1, None, 1, 1, 10, 50, None),
                    (1, 14, 1, None, 1, 1, 10, 50, None),
                    (1, 9, 1, None, 1, 3, 99, 999, None),
                ],
            )

    async def test_loads_legacy_templates_and_excludes_empty_inactive_and_historical_rows(self):
        self.seed_legacy_templates()
        before = self.fixture.rows()
        status, body, headers = await self.request(
            "GET", "/users/2/routine", include_headers=True,
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["storage_format"], "legacy")
        self.assertEqual(headers[b"x-routine-id"], b"11")
        self.assertEqual([day["routine_id"] for day in body["days"]], [9, 10, 11])
        self.assertEqual([day["day"] for day in body["days"]], [1, 2, 3])
        self.assertTrue(all(day["duration_minutes"] is None for day in body["days"]))
        exercise = body["days"][0]["exercises"][0]
        self.assertEqual(exercise["sets"], 2)
        self.assertEqual(exercise["reps"], "8 / 6")
        self.assertEqual(exercise["name"], "Bench Press")
        self.assertIsNone(exercise["rest_seconds"])
        self.assertIn("weight=75.0", exercise["notes"])
        self.assertIn("duration_seconds=60", body["days"][1]["exercises"][0]["notes"])
        self.assertNotIn("999", exercise["notes"])
        self.assertEqual(self.fixture.rows(), before)
        self.assertEqual((await self.request("PUT", "/users/2/routine", body))[0], 422)
        self.assertEqual(self.fixture.rows(), before)

    async def test_legacy_empty_templates_return_null_without_version_header(self):
        self.seed_legacy_templates()
        with sqlite3.connect(self.fixture.database) as db:
            db.execute("DELETE FROM fact_workout_sets WHERE training_id IS NULL")
        status, body, headers = await self.request(
            "GET", "/users/2/routine", include_headers=True,
        )
        self.assertEqual((status, body), (200, None))
        self.assertNotIn(b"x-routine-id", headers)

    async def test_new_json_save_replaces_legacy_read_without_changing_old_descriptions(self):
        self.seed_legacy_templates()
        before = self.fixture.rows()
        status, saved = await self.request("PUT", "/users/2/routine", test_routine_maker.plan())
        self.assertEqual(status, 200)
        self.assertEqual(await self.request("GET", "/users/2/routine"), (200, saved))
        self.assertEqual(
            [row[:4] for row in self.fixture.rows()[:-1]],
            [row[:4] for row in before],
        )

    async def test_replaces_only_selected_users_active_routines(self):
        original = self.fixture.saved()
        await self.request("PUT", "/users/2/routine", test_routine_maker.plan())
        before = self.fixture.rows()
        payload = original.routine.model_dump(mode="json")
        payload["name"] = "Updated routine"
        payload["days"][0]["exercises"][0]["sets"] = 4
        status, saved = await self.request("PUT", "/users/1/routine", payload)
        self.assertEqual((status, saved), (200, payload))
        rows = self.fixture.rows()
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0][4], 0)
        self.assertEqual(rows[0][:4], before[0][:4])
        self.assertEqual(rows[1], before[1])
        self.assertEqual(rows[2][1], 1)
        self.assertEqual(rows[2][4], 1)
        self.assertEqual(await self.request("GET", "/users/1/routine"), (200, payload))
        self.assertEqual(
            await self.request("GET", "/users/2/routine"),
            (200, json.loads(before[1][3])["routine"]),
        )

    async def test_invalid_input_preserves_existing_routine(self):
        self.fixture.saved()
        before = self.fixture.rows()
        invalid = []
        for field, value in (
            ("exercise_id", 999), ("sets", 0), ("unexpected", True),
        ):
            payload = test_routine_maker.plan()
            payload["days"][0]["exercises"][0][field] = value
            invalid.append(payload)
        payload = test_routine_maker.plan()
        payload["days"][1]["day"] = 1
        invalid.append(payload)
        payload = test_routine_maker.plan()
        payload["days"][0]["exercises"] *= 2
        invalid.append(payload)
        invalid.extend(({}, {"routine": test_routine_maker.plan()}))
        for payload in invalid:
            with self.subTest(payload=payload):
                status, result = await self.request("PUT", "/users/1/routine", payload)
                self.assertEqual(status, 422)
                self.assertIn("detail", result)
                self.assertEqual(self.fixture.rows(), before)

    async def test_unknown_or_invalid_user_does_not_write(self):
        for user_id, expected_status in ((999, 404), (0, 422), (-1, 422), ("bad", 422)):
            with self.subTest(user_id=user_id):
                status, _ = await self.request(
                    "PUT", f"/users/{user_id}/routine", test_routine_maker.plan(),
                )
                self.assertEqual(status, expected_status)
                self.assertEqual(self.fixture.rows(), [])

    async def test_insert_failure_rolls_back_active_flags(self):
        self.fixture.saved()
        before = self.fixture.rows()
        with sqlite3.connect(self.fixture.database) as db:
            db.execute(
                "CREATE TRIGGER reject_routine BEFORE INSERT ON dim_routines "
                "BEGIN SELECT RAISE(ABORT, 'insert failed'); END"
            )
        status, _ = await self.request(
            "PUT", "/users/1/routine", test_routine_maker.plan(),
            expected_error=sqlite3.IntegrityError,
        )
        self.assertEqual(status, 500)
        self.assertEqual(self.fixture.rows(), before)

    def test_openapi_documents_complete_routine_body(self):
        operation = app.openapi()["paths"]["/users/{user_id}/routine"]["put"]
        self.assertEqual(
            operation["requestBody"]["content"]["application/json"]["schema"],
            {"$ref": "#/components/schemas/RoutinePlan"},
        )
        self.assertEqual(
            operation["responses"]["200"]["content"]["application/json"]["schema"],
            {"$ref": "#/components/schemas/RoutinePlan"},
        )
        self.assertIn("404", operation["responses"])
