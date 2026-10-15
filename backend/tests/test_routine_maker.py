import json
import sqlite3
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch

from pydantic import ValidationError

from api.redis_deps import RedisClient
from systems.routinemaker.RoutineMaker import RoutineMaker
from utils.general.GeminiApiCall import GeminiClient
from utils.routinemaker.dataclass.models import RoutineParameters, RoutinePlan, RoutineState
from utils.routinemaker.func.repository import RoutineInputError
from utils.routinemaker.func.handle import save_draft


COMPLETE = {
    "routine_type": "ppl", "days_per_week": 3,
    "hours_per_session": 1.0, "level": "beginner",
}


def decision(intent="create", parameters=None, **kwargs):
    return json.dumps({
        "intent": intent, "parameters": parameters or {}, "message": "", **kwargs,
    })


def plan():
    return {
        "name": "Three-day PPL",
        "summary": "Three focused sessions balance pushing, pulling and leg training with recovery days.",
        "days": [
            {
                "day": number, "day_type": kind, "info": "Warm up for five minutes.",
                "duration_minutes": 45,
                "exercises": [{
                    "exercise_id": exercise_id, "sets": 3, "reps": "8-12",
                    "rest_seconds": 90, "notes": "Leave two reps in reserve.",
                }],
            }
            for number, kind, exercise_id in ((1, "push", 1), (2, "pull", 5), (3, "legs", 3))
        ],
        "recovery": "Rest between training days. Progress gradually.",
    }


class RoutineMakerTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = Path(directory.name) / "gym.db"
        source = Path(__file__).resolve().parents[2] / "database/gym_app.db"
        with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as original:
            ddl = [
                original.execute("SELECT sql FROM sqlite_master WHERE name = ?", (name,)).fetchone()[0]
                for name in ("dim_users", "dim_exercises", "dim_routines")
            ]
        with sqlite3.connect(self.database) as db:
            for statement in ddl:
                db.execute(statement)
            db.executemany("INSERT INTO dim_users(id, username) VALUES (?, ?)", [(1, "first"), (2, "second")])
            for exercise_id, name, level, pattern, muscle in (
                (1, "Bench Press", "beginner", "push", "chest"),
                (2, "Intermediate Row", "intermediate", "pull", "back"),
                (3, "Squat", "beginner", "legs", "quads"),
                (4, "Advanced Press", "advanced", "push", "shoulders"),
                (5, "Pulldown", "beginner", "pull", "back"),
                (6, "Push Up", "beginner", "push", "chest"),
            ):
                db.execute(
                    "INSERT INTO dim_exercises "
                    "(id, name, instructions, primary_muscle, pattern, equipment, mechanic, level, intensity) "
                    "VALUES (?, ?, 'Instructions', ?, ?, 'bodyweight', 'compound', ?, 'medium')",
                    (exercise_id, name, muscle, pattern, level),
                )
        self.client = Mock(spec=GeminiClient)
        self.store = RedisClient()
        self.maker = RoutineMaker(self.client, database_path=self.database, state_store=self.store)

    def turn(self, *responses, query="Make a routine", session_id="session", user_id=1, **kwargs):
        self.client.generate.side_effect = list(responses)
        return self.maker.handle(query, session_id=session_id, user_id=user_id, **kwargs)

    def draft(self):
        return self.turn(decision(parameters=COMPLETE), json.dumps(plan()))

    def saved(self):
        self.draft()
        return self.turn(decision("save"), query="Yes, save it")

    def rows(self):
        with sqlite3.connect(self.database) as db:
            return db.execute("SELECT id, user_id, name, description, is_active FROM dim_routines ORDER BY id").fetchall()

    def state(self, session_id="session", user_id=1):
        raw = self.store.get_routine_state(session_id, user_id)
        return RoutineState.model_validate_json(raw) if raw else None

    def test_first_api_call_classifies_and_plan_is_cached_without_saving(self):
        result = self.draft()
        self.assertEqual(result.status, "awaiting_confirmation")
        self.assertEqual(len(result.routine.days), 3)
        self.assertEqual(result.routine.days[0].day_type, "push")
        self.assertEqual(result.routine.days[0].exercises[0].name, "Bench Press")
        self.assertEqual(self.rows(), [])
        self.assertTrue(self.state().awaiting_confirmation)
        calls = self.client.generate.call_args_list
        self.assertEqual(calls[0].kwargs["system_prompt"], self.maker._prompts["routing"])
        self.assertEqual(calls[0].kwargs["response_mime_type"], "application/json")
        self.assertEqual(calls[1].kwargs["response_mime_type"], "application/json")
        catalog = json.loads(calls[1].args[0])["exercises"]
        self.assertEqual({item["id"] for item in catalog}, {1, 3, 5, 6})

    def test_missing_parameters_are_collected_across_new_instances(self):
        first = self.turn(decision(parameters={"routine_type": "ppl"}), "Days, time and level?")
        self.assertEqual(first.status, "needs_parameters")
        self.maker = RoutineMaker(self.client, database_path=self.database, state_store=self.store)
        result = self.turn(
            decision(parameters={key: value for key, value in COMPLETE.items() if key != "routine_type"}),
            json.dumps(plan()), query="Three days, one hour, beginner",
        )
        self.assertEqual(result.parameters.model_dump(), COMPLETE)
        self.assertEqual(result.status, "awaiting_confirmation")
        self.assertEqual(self.rows(), [])

    def test_invalid_user_requirement_clears_known_value_and_asks_again(self):
        self.draft()
        result = self.turn(
            decision("update_draft", {"routine_type": None}), "Weider or PPL?",
        )
        self.assertEqual(result.status, "needs_parameters")
        self.assertIsNone(result.parameters.routine_type)
        self.assertFalse(self.state().awaiting_confirmation)

    def test_save_requires_separate_confirmation_and_is_persistent(self):
        preview = self.draft()
        result = self.turn(decision("save"), query="Yes, save it")
        self.assertEqual(result.status, "saved")
        self.assertEqual(result.routine_id, self.rows()[0][0])
        self.assertEqual(self.rows()[0][4], 1)
        stored, parameters = self.maker._repository.load(1, result.routine_id)
        self.assertEqual(stored, preview.routine)
        self.assertEqual(parameters.model_dump(), COMPLETE)
        self.assertFalse(self.state().awaiting_confirmation)
        self.assertEqual(self.client.generate.call_count, 3)

    def test_repeated_confirmation_does_not_create_duplicates(self):
        self.saved()
        result = self.turn(decision("save"), query="Save it again")
        self.assertEqual(result.status, "needs_routine")
        self.assertEqual(len(self.rows()), 1)

    def test_save_is_idempotent_if_cache_write_failed_after_database_commit(self):
        self.draft()
        state = self.state()
        repository = self.maker._repository
        first = repository.save(1, state.routine, state.parameters, state.draft_id, None)
        second = repository.save(1, state.routine, state.parameters, state.draft_id, None)
        self.assertEqual(first, second)
        self.assertEqual(len(self.rows()), 1)

    def test_save_without_preview_never_writes(self):
        result = self.turn(decision("save"))
        self.assertEqual(result.status, "needs_routine")
        self.assertEqual(self.rows(), [])

    def test_refusal_preserves_draft_without_saving(self):
        before = self.draft()
        result = self.turn(decision("no_match", message="Nothing has been saved."), query="No")
        self.assertEqual(result.status, "no_match")
        self.assertEqual(result.routine, before.routine)
        self.assertEqual(self.rows(), [])

    def test_completely_new_request_discards_previous_parameters(self):
        self.draft()
        result = self.turn(decision(start_new=True, parameters={"routine_type": "weider"}), "Days, time and level?")
        self.assertEqual(result.status, "needs_parameters")
        self.assertIsNone(result.parameters.days_per_week)
        self.assertIsNone(result.routine)
        self.assertFalse(self.state().awaiting_confirmation)

    def test_draft_modification_asks_for_missing_edit_details_then_resumes(self):
        self.draft()
        first = self.turn(decision("update_draft"), "Which day and exercise, and what change?")
        self.assertEqual(first.status, "needs_changes")
        self.assertFalse(self.state().awaiting_confirmation)
        changed = plan()
        changed["days"][0]["exercises"][0]["sets"] = 4
        result = self.turn(
            decision("update_draft", change={"action": "adjust", "day": 1, "exercise_id": 1, "details": "Four sets"}),
            json.dumps(changed),
        )
        self.assertEqual(result.status, "awaiting_confirmation")
        self.assertEqual(result.routine.days[0].exercises[0].sets, 4)
        self.assertEqual(self.rows(), [])

    def test_incomplete_edit_cannot_save_the_old_preview(self):
        self.draft()
        self.turn(decision("update_draft", change={"action": "replace"}), "Which exercise?")
        result = self.turn(decision("save"))
        self.assertEqual(result.status, "needs_routine")
        self.assertEqual(self.rows(), [])

    def test_replace_merges_change_parameters_across_turns(self):
        self.draft()
        self.turn(decision("update_draft", change={"action": "replace", "day": 1}), "Which exercises?")
        changed = plan()
        changed["days"][0]["exercises"][0]["exercise_id"] = 6
        result = self.turn(
            decision("update_draft", change={"exercise_id": 1, "replacement_exercise_id": 6}),
            json.dumps(changed),
        )
        self.assertEqual(result.routine.days[0].exercises[0].exercise_id, 6)
        self.assertEqual(result.routine.days[0].exercises[0].name, "Push Up")

    def test_add_and_remove_preserve_other_exercises(self):
        self.draft()
        changed = plan()
        changed["days"][0]["exercises"].append({**changed["days"][0]["exercises"][0], "exercise_id": 6})
        result = self.turn(
            decision("update_draft", change={"action": "add", "day": 1, "exercise_id": 6}),
            json.dumps(changed),
        )
        self.assertEqual(len(result.routine.days[0].exercises), 2)
        result = self.turn(
            decision("update_draft", change={"action": "remove", "day": 1, "exercise_id": 6}),
            json.dumps(plan()),
        )
        self.assertEqual(len(result.routine.days[0].exercises), 1)

    def test_saved_modification_loads_context_and_saves_new_active_version(self):
        saved = self.saved()
        with sqlite3.connect(self.database) as db:
            db.execute("UPDATE dim_routines SET is_active = 1 WHERE id = ?", (saved.routine_id,))
        original = self.rows()[0]
        changed = plan()
        changed["days"][0]["exercises"][0]["exercise_id"] = 6
        result = self.turn(
            decision("update_saved", routine_id=saved.routine_id, change={
                "action": "replace", "day": 1, "exercise_id": 1, "replacement_exercise_id": 6,
            }),
            json.dumps(changed), session_id="another-session",
        )
        self.assertEqual(result.status, "awaiting_confirmation")
        payload = json.loads(self.client.generate.call_args.args[0])
        self.assertEqual(payload["routine"]["days"][0]["exercises"][0]["exercise_id"], 1)
        self.assertEqual(self.rows(), [original])
        result = self.turn(decision("save"), session_id="another-session")
        self.assertEqual(result.status, "saved")
        self.assertNotEqual(result.routine_id, saved.routine_id)
        self.assertEqual(self.rows()[0][:4], original[:4])
        self.assertEqual(self.rows()[0][4], 0)
        self.assertEqual(self.rows()[1][4], 1)
        self.assertEqual(json.loads(self.rows()[1][3])["source_routine_id"], saved.routine_id)

    def test_selecting_saved_routine_asks_when_ambiguous(self):
        self.saved()
        self.saved()
        with sqlite3.connect(self.database) as db:
            db.execute("UPDATE dim_routines SET is_active = 0")
        result = self.turn(decision("update_saved"), session_id="new")
        self.assertEqual(result.status, "needs_routine")
        self.assertIn("Three-day PPL", result.message)
        self.assertIn("newest first", result.message)
        self.assertNotRegex(result.message, r"(?i)\bid\b|routine_id|is_active|\d")
        self.assertEqual(self.state("new").workflow, "update_saved")

    def test_routine_selection_messages_offer_names_without_ids_in_both_languages(self):
        first = self.saved()
        second = self.saved()
        with sqlite3.connect(self.database) as db:
            db.execute("UPDATE dim_routines SET name = 'Earlier split', is_active = 0 WHERE id = ?", (first.routine_id,))
            db.execute("UPDATE dim_routines SET name = 'Latest split', is_active = 0 WHERE id = ?", (second.routine_id,))
        for language in ("EN", "ES"):
            result = self.turn(
                decision("update_saved"), session_id=f"selection-{language}", language=language,
            )
            self.assertEqual(result.status, "needs_routine")
            self.assertIn("- Latest split\n- Earlier split", result.message)
            self.assertNotRegex(result.message, r"(?i)\bid\b|routine_id|is_active|\d")

    def test_no_saved_routines_asks_to_create_one_without_ids(self):
        for language in ("EN", "ES"):
            result = self.turn(
                decision("update_saved"), session_id=f"empty-{language}", language=language,
            )
            self.assertEqual(result.status, "needs_routine")
            self.assertNotRegex(result.message, r"(?i)\bid\b|routine_id|is_active")
            self.assertIn("Create" if language == "EN" else "Crea", result.message)

    def test_routine_prompts_keep_database_ids_out_of_user_facing_text(self):
        for stage in ("routing", "parameters", "routine_maker", "routine_updater"):
            with self.subTest(stage=stage):
                self.assertIn("Database IDs are internal only.", self.maker._prompts[stage])
                self.assertIn("Never show or ask for IDs", self.maker._prompts[stage])

    def test_edit_details_survive_saved_routine_selection(self):
        saved = self.saved()
        self.saved()
        with sqlite3.connect(self.database) as db:
            db.execute("UPDATE dim_routines SET is_active = 0")
        first = self.turn(decision("update_saved", change={
            "action": "replace", "day": 1, "exercise_id": 1, "replacement_exercise_id": 6,
        }), session_id="selection")
        self.assertEqual(first.status, "needs_routine")
        changed = plan()
        changed["days"][0]["exercises"][0]["exercise_id"] = 6
        result = self.turn(
            decision("update_saved", routine_id=saved.routine_id),
            json.dumps(changed), session_id="selection",
        )
        self.assertEqual(result.status, "awaiting_confirmation")
        self.assertEqual(result.parameters.model_dump(), COMPLETE)
        self.assertEqual(result.routine.days[0].exercises[0].exercise_id, 6)

    def test_parameter_changes_survive_saved_routine_selection(self):
        saved = self.saved()
        self.saved()
        with sqlite3.connect(self.database) as db:
            db.execute("UPDATE dim_routines SET is_active = 0")
        self.turn(decision("update_saved", {"days_per_week": 2}), session_id="selection")
        changed = plan()
        changed["days"].pop()
        result = self.turn(
            decision("update_saved", routine_id=saved.routine_id),
            json.dumps(changed), session_id="selection",
        )
        self.assertEqual(result.status, "awaiting_confirmation")
        self.assertEqual(len(result.routine.days), 2)

    def test_update_automatically_loads_current_routine_among_multiple_versions(self):
        self.saved()
        current = self.saved()
        changed = plan()
        changed["days"][0]["exercises"][0]["sets"] = 4
        result = self.turn(
            decision("update_saved", change={
                "action": "adjust", "day": 1, "exercise_id": 1, "details": "4 sets",
            }),
            json.dumps(changed), session_id="current",
        )
        self.assertEqual(result.status, "awaiting_confirmation")
        self.assertEqual(self.state("current").source_routine_id, current.routine_id)
        self.assertEqual(len(self.rows()), 2)

    def test_direct_save_is_model_free_and_idempotent(self):
        preview = self.draft()
        self.client.generate.reset_mock()
        for _ in range(2):
            result = save_draft(
                repository=self.maker._repository, state_store=self.store,
                session_id="session", user_id=1, draft_id=preview.draft_id,
            )
            self.assertEqual(result.status, "saved")
            self.assertEqual(result.routine, preview.routine)
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.rows()[0][4], 1)
        self.client.generate.assert_not_called()

    def test_direct_save_rejects_stale_preview_after_incomplete_edit(self):
        preview = self.draft()
        self.turn(decision("update_draft"), "What changes?")
        result = save_draft(
            repository=self.maker._repository, state_store=self.store,
            session_id="session", user_id=1, draft_id=preview.draft_id,
        )
        self.assertEqual(result.status, "needs_routine")
        self.assertEqual(self.rows(), [])

    def test_direct_save_retry_after_cache_failure_does_not_duplicate_or_reactivate(self):
        preview = self.draft()
        with patch.object(self.store, "set_routine_state", side_effect=RuntimeError("Cache unavailable")):
            with self.assertRaisesRegex(RuntimeError, "Cache unavailable"):
                save_draft(
                    repository=self.maker._repository, state_store=self.store,
                    session_id="session", user_id=1, draft_id=preview.draft_id,
                )
        self.assertEqual(len(self.rows()), 1)
        old_id = self.rows()[0][0]
        self.turn(decision(parameters=COMPLETE), json.dumps(plan()), session_id="new-session")
        current = self.turn(decision("save"), session_id="new-session")
        result = save_draft(
            repository=self.maker._repository, state_store=self.store,
            session_id="session", user_id=1, draft_id=preview.draft_id,
        )
        self.assertEqual(result.routine_id, old_id)
        self.assertEqual(
            [(row[0], row[4]) for row in self.rows()],
            [(old_id, 0), (current.routine_id, 1)],
        )

    def test_saving_new_version_only_changes_its_owners_active_selection(self):
        first = self.saved()
        self.turn(decision(parameters=COMPLETE), json.dumps(plan()), user_id=2)
        other = self.turn(decision("save"), user_id=2)
        current = self.saved()
        self.assertEqual(
            [(row[0], row[1], row[4]) for row in self.rows()],
            [(first.routine_id, 1, 0), (other.routine_id, 2, 1), (current.routine_id, 1, 1)],
        )

    def test_failed_insert_rolls_back_active_selection(self):
        first = self.saved()
        preview = self.draft()
        with sqlite3.connect(self.database) as db:
            db.execute(
                "CREATE TRIGGER fail_save BEFORE INSERT ON dim_routines "
                "BEGIN SELECT RAISE(ABORT, 'Save failed'); END"
            )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "Save failed"):
            save_draft(
                repository=self.maker._repository, state_store=self.store,
                session_id="session", user_id=1, draft_id=preview.draft_id,
            )
        self.assertEqual([(row[0], row[4]) for row in self.rows()], [(first.routine_id, 1)])
        self.assertTrue(self.state().awaiting_confirmation)

    def test_exact_minimum_and_maximum_training_day_counts(self):
        for count in (1, 7):
            generated = plan()
            generated["days"] = [
                {**deepcopy(generated["days"][index % 3]), "day": index + 1}
                for index in range(count)
            ]
            result = self.turn(
                decision(parameters={**COMPLETE, "days_per_week": count}),
                json.dumps(generated), session_id=f"days-{count}",
            )
            self.assertEqual(len(result.routine.days), count)

    def test_foreign_owned_saved_routine_is_rejected(self):
        saved = self.saved()
        with self.assertRaisesRegex(RoutineInputError, "belong"):
            self.turn(decision("update_saved", routine_id=saved.routine_id), user_id=2)

    def test_cache_is_isolated_by_session_and_user(self):
        self.draft()
        for session_id, user_id in (("other", 1), ("session", 2)):
            with self.subTest(session=session_id, user=user_id):
                result = self.turn(decision("save"), session_id=session_id, user_id=user_id)
                self.assertEqual(result.status, "needs_routine")
        self.assertEqual(self.rows(), [])

    def test_routine_metadata_does_not_break_conversation_turn_ids(self):
        self.draft()
        self.assertEqual(self.store.add_turn("session", "query", "response", "routine_maker"), 1)
        self.assertEqual(self.store.turn_count("session"), 1)
        self.assertEqual(len(self.store.get_session("session")), 1)

    def test_invalid_routing_is_retried_with_pydantic_errors(self):
        result = self.turn(
            decision("not_allowed"), decision("update"), decision(parameters=COMPLETE), json.dumps(plan()),
        )
        self.assertEqual(result.status, "awaiting_confirmation")
        calls = self.client.generate.call_args_list
        self.assertIn("validation_error", json.loads(calls[1].args[0]))
        self.assertEqual(len(calls), 4)

    def test_three_invalid_intents_fail_without_cache_or_writes(self):
        with self.assertRaises(ValidationError):
            self.turn(decision("bad"), decision("bad"), decision("bad"))
        self.assertIsNone(self.state())
        self.assertEqual(self.rows(), [])

    def test_empty_json_response_is_retried_by_pydantic(self):
        result = self.turn(" ", decision(parameters=COMPLETE), json.dumps(plan()))
        self.assertEqual(result.status, "awaiting_confirmation")

    def test_invalid_generation_is_retried_for_actual_output_constraints(self):
        invalid_plans = []
        unknown = plan()
        unknown["days"][0]["exercises"][0]["exercise_id"] = 999
        invalid_plans.append(unknown)
        advanced = plan()
        advanced["days"][0]["exercises"][0]["exercise_id"] = 4
        invalid_plans.append(advanced)
        wrong_days = plan()
        wrong_days["days"].pop()
        invalid_plans.append(wrong_days)
        too_long = plan()
        too_long["days"][0]["duration_minutes"] = 61
        invalid_plans.append(too_long)
        duplicate_days = plan()
        duplicate_days["days"][1]["day"] = 1
        invalid_plans.append(duplicate_days)
        duplicate_exercise = plan()
        duplicate_exercise["days"][0]["exercises"] *= 2
        invalid_plans.append(duplicate_exercise)
        for index, invalid in enumerate(invalid_plans):
            with self.subTest(index=index):
                result = self.turn(
                    decision(parameters=COMPLETE), json.dumps(invalid), json.dumps(plan()),
                    session_id=f"invalid-{index}",
                )
                self.assertEqual(result.status, "awaiting_confirmation")
                payload = json.loads(self.client.generate.call_args.args[0])
                self.assertIn("validation_error", payload)

    def test_three_invalid_plans_fail_without_cache_or_save(self):
        invalid = json.dumps({"name": "No days"})
        with self.assertRaises(ValidationError):
            self.turn(decision(parameters=COMPLETE), invalid, invalid, invalid)
        self.assertIsNone(self.state())
        self.assertEqual(self.rows(), [])

    def test_json_catalog_and_summary_errors_use_exactly_three_generation_attempts(self):
        unknown = plan()
        unknown["days"][0]["exercises"][0]["exercise_id"] = 999
        self.client.generate.reset_mock()
        result = self.turn(
            decision(parameters=COMPLETE), '{"name":',
            json.dumps(unknown), json.dumps(plan()),
        )
        self.assertEqual(result.status, "awaiting_confirmation")
        self.assertEqual(result.routine.summary, plan()["summary"])
        calls = self.client.generate.call_args_list
        self.assertEqual(len(calls), 4)  # One routing call, three generation calls.
        self.assertIn("json_invalid", json.loads(calls[2].args[0])["validation_error"])
        self.assertIn("unknown exercise", json.loads(calls[3].args[0])["validation_error"])
        self.assertEqual(self.rows(), [])

    def test_three_unknown_catalog_outputs_raise_pydantic_error_without_state_or_database_write(self):
        invalid = plan()
        invalid["days"][0]["exercises"][0]["exercise_id"] = 999
        self.client.generate.reset_mock()
        with self.assertRaisesRegex(ValidationError, "unknown exercise"):
            self.turn(
                decision(parameters=COMPLETE),
                *[json.dumps(invalid)] * 3,
            )
        self.assertEqual(self.client.generate.call_count, 4)
        self.assertIsNone(self.state())
        self.assertEqual(self.rows(), [])

    def test_generation_requires_brief_summary_and_preserves_previous_preview_after_failure(self):
        before = self.draft()
        for summary in ("", " " * 4, "x" * 601):
            invalid = plan()
            invalid["summary"] = summary
            with self.subTest(summary=summary), self.assertRaises(ValidationError):
                self.turn(
                    decision("update_draft", {"hours_per_session": 2.0}),
                    *[json.dumps(invalid)] * 3,
                )
            self.assertEqual(self.state().routine, before.routine)
            self.assertEqual(self.state().draft_id, before.draft_id)
        self.assertEqual(self.rows(), [])

    def test_saved_legacy_plan_without_summary_still_loads_and_validates(self):
        saved = self.saved()
        with sqlite3.connect(self.database) as db:
            db.execute(
                "UPDATE dim_routines SET description = json_remove(description, '$.routine.summary') WHERE id = ?",
                (saved.routine_id,),
            )
        stored, parameters = self.maker._repository.load(1, saved.routine_id)
        self.assertEqual(stored.summary, "")
        self.maker._repository.validate_plan(stored, parameters)

    def test_update_rejects_unrelated_changes_and_retries(self):
        self.draft()
        changed = plan()
        changed["days"][0]["exercises"][0]["sets"] = 4
        unrelated = deepcopy(changed)
        unrelated["days"][1]["exercises"][0]["sets"] = 5
        result = self.turn(
            decision("update_draft", change={"action": "adjust", "day": 1, "exercise_id": 1, "details": "4 sets"}),
            json.dumps(unrelated), json.dumps(changed),
        )
        self.assertEqual(result.routine.days[1].exercises[0].sets, 3)

    def test_invalid_modification_target_asks_instead_of_generating(self):
        self.draft()
        self.client.generate.reset_mock()
        result = self.turn(decision("update_draft", change={"action": "remove", "day": 2, "exercise_id": 1}))
        self.assertEqual(result.status, "needs_changes")
        self.assertIn("by name", result.message)
        self.assertNotRegex(result.message, r"(?i)\bid\b|exercise_id")
        self.client.generate.assert_called_once()

    def test_invalid_exercise_selection_asks_by_name_in_spanish(self):
        self.draft()
        result = self.turn(
            decision("update_draft", change={"action": "remove", "day": 2, "exercise_id": 1}),
            language="ES",
        )
        self.assertEqual(result.status, "needs_changes")
        self.assertIn("por su nombre", result.message)
        self.assertNotRegex(result.message, r"(?i)\bid\b|exercise_id")

    def test_provider_errors_are_not_retried_or_hidden(self):
        self.client.generate.side_effect = ValueError("Provider configuration failed")
        with self.assertRaisesRegex(ValueError, "Provider configuration"):
            self.maker.handle("Make routine", session_id="session", user_id=1)
        self.client.generate.assert_called_once()

    def test_invalid_user_and_session_fail_before_api(self):
        for kwargs in (
            {"user_id": 999}, {"user_id": True}, {"user_id": 0},
            {"session_id": ""}, {"query": " "}, {"language": "FR"},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(RoutineInputError):
                self.maker.handle(**{"query": "Make a routine", "session_id": "session", "user_id": 1, **kwargs})
        self.client.generate.assert_not_called()

    def test_catalog_names_are_not_generated_or_trusted(self):
        generated = plan()
        generated["days"][0]["exercises"][0]["name"] = "Invented"
        result = self.turn(decision(parameters=COMPLETE), json.dumps(generated))
        self.assertEqual(result.routine.days[0].exercises[0].name, "Bench Press")

    def test_parameter_only_update_can_change_the_number_of_days(self):
        self.draft()
        changed = plan()
        changed["days"].pop()
        result = self.turn(
            decision("update_draft", {"days_per_week": 2}),
            json.dumps(changed), query="Change it to two training days",
        )
        self.assertEqual(result.status, "awaiting_confirmation")
        self.assertEqual(len(result.routine.days), 2)
        self.assertEqual(self.rows(), [])

    def test_original_preferences_survive_parameter_collection(self):
        self.turn(decision(parameters={"routine_type": "ppl"}), "Days, time and level?", query="PPL on Monday, Wednesday and Friday")
        self.turn(decision(parameters=COMPLETE), json.dumps(plan()), query="Three days, one hour, beginner")
        payload = json.loads(self.client.generate.call_args.args[0])
        self.assertIn("Monday", payload["requests"][0])

    def test_save_with_edits_is_not_an_allowed_confirmation(self):
        self.draft()
        result = self.turn(
            decision("save", change={"action": "replace"}),
            decision("update_draft"), "Which exercise should I replace?",
        )
        self.assertEqual(result.status, "needs_changes")
        self.assertEqual(self.rows(), [])

    def test_removing_only_exercise_asks_instead_of_generating_empty_day(self):
        self.draft()
        result = self.turn(decision("update_draft", change={"action": "remove", "day": 1, "exercise_id": 1}))
        self.assertEqual(result.status, "needs_changes")
        self.assertIn("at least one", result.message)

    def test_save_revalidates_database_catalog_before_writing(self):
        self.draft()
        with sqlite3.connect(self.database) as db:
            db.execute("DELETE FROM dim_exercises WHERE id = 1")
        with self.assertRaisesRegex(ValueError, "unknown exercise"):
            self.turn(decision("save"))
        self.assertEqual(self.rows(), [])

    def test_invalid_parameter_model_rejects_unsupported_values(self):
        for value in ({"days_per_week": True}, {"days_per_week": 8}, {"hours_per_session": 0}, {"level": "expert"}):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                RoutineParameters.model_validate(value)


if __name__ == "__main__":
    unittest.main()
