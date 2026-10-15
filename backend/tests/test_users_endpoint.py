import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from api.Endpoint.active_routine import get_routine_repository
from api.user_deps import UserRepository, get_user_repository
from api.redis_deps import RedisClient, SetKey, get_routine_store, get_set_key
from app import app
import test_chat_endpoint
import test_routine_maker


class UserEndpointTests(unittest.IsolatedAsyncioTestCase):
    request = test_chat_endpoint.ChatEndpointTests.request

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "users.db"
        with sqlite3.connect(path) as db:
            db.execute(
                "CREATE TABLE dim_users (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "username TEXT NOT NULL UNIQUE, weight_unit TEXT NOT NULL DEFAULT 'kg' "
                "CHECK(weight_unit IN ('kg', 'lbs')))"
            )
        repository = UserRepository(path)
        self.store = RedisClient()
        for dependency, override in (
            (get_user_repository, lambda: repository),
            (get_routine_store, lambda: self.store),
            (get_set_key, lambda: SetKey(self.store)),
        ):
            app.dependency_overrides[dependency] = override
            self.addCleanup(app.dependency_overrides.pop, dependency)

    async def test_active_routine_returns_saved_plan_or_null_for_user(self):
        fixture = test_routine_maker.RoutineMakerTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        app.dependency_overrides[get_routine_repository] = lambda: fixture.maker._repository
        self.addCleanup(app.dependency_overrides.pop, get_routine_repository)

        self.assertEqual(await self.request("GET", "/users/1/routine"), (200, None))
        saved = fixture.saved()
        status, routine = await self.request("GET", "/users/1/routine")
        self.assertEqual(status, 200)
        self.assertEqual(routine, saved.routine.model_dump(mode="json"))
        self.assertEqual(await self.request("GET", "/users/2/routine"), (200, None))
        status, _ = await self.request("GET", "/users/999/routine")
        self.assertEqual(status, 404)
        status, _ = await self.request("GET", "/users/0/routine")
        self.assertEqual(status, 422)

    async def test_one_persistent_default_and_registration(self):
        status, users = await self.request("GET", "/users")
        self.assertEqual(status, 200)
        self.assertEqual(users, [{"id": 1, "username": "Jamie Davis", "weight_unit": "kg"}])
        self.assertEqual((await self.request("GET", "/users"))[1], users)
        status, created = await self.request(
            "POST", "/users", {"username": "  Alex  ", "weight_unit": "lbs"}
        )
        self.assertEqual(status, 201)
        self.assertEqual(created, {"id": 2, "username": "Alex", "weight_unit": "lbs"})
        self.assertEqual((await self.request("GET", "/users"))[1], users + [created])
        status, _ = await self.request("POST", "/users", {"username": "Alex"})
        self.assertEqual(status, 409)
        self.assertEqual(len((await self.request("GET", "/users"))[1]), 2)

    async def test_invalid_registration_does_not_write(self):
        for payload in (
            {"username": "  "}, {"username": "x" * 81}, {"username": 123},
            {"username": "Alex", "weight_unit": "stones"},
            {"username": "Alex", "unexpected": True},
        ):
            status, _ = await self.request("POST", "/users", payload)
            self.assertEqual(status, 422)
        self.assertEqual(len((await self.request("GET", "/users"))[1]), 1)

    async def test_switch_initialization_preserves_other_users_and_existing_context(self):
        await self.request("POST", "/1/key")
        self.store.add_turn("1", "Question", "Answer", "no_system")
        status, result = await self.request("POST", "/2/key")
        self.assertEqual((status, result), (200, {"id": "2", "created": True}))
        status, result = await self.request("POST", "/1/key")
        self.assertEqual((status, result), (200, {"id": "1", "created": False}))
        self.assertEqual(self.store.turn_count("1"), 1)

    async def test_new_conversation_resets_only_selected_users_context(self):
        for session in ("1", "2"):
            await self.request("POST", f"/{session}/key")
            self.store.add_turn(session, "Question", "Answer", "no_system")
            self.store.set_routine_state(session, int(session), "draft")
        status, result = await self.request("POST", "/1/key?reset=true")
        self.assertEqual((status, result), (200, {"id": "1", "created": True}))
        self.assertEqual(self.store.turn_count("1"), 0)
        self.assertIsNone(self.store.get_routine_state("1", 1))
        self.assertEqual(self.store.turn_count("2"), 1)
        self.assertEqual(self.store.get_routine_state("2", 2), "draft")
