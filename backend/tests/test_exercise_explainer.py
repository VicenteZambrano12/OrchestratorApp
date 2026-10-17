import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from systems.exercise_explainer.ExerciseExplainer import ExerciseExplainer
from utils.exercise_explainer.dataclass.models import ExerciseExplanation
from utils.exercise_explainer.func.catalog import (
    MIN_MATCH_MARGIN,
    MIN_MATCH_SCORE,
    ExerciseCatalog,
    match_score,
    normalize_name,
)
from utils.exercise_explainer.func.generate import generate
from utils.exercise_explainer.func.handle import handle
from utils.exercise_explainer.func.load_prompts import load_prompts
from utils.general.GeminiApiCall import GeminiClient


def decision(exercises, message=""):
    return json.dumps({"exercises": exercises, "message": message})


class ExerciseExplainerTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "catalog.db"
        with sqlite3.connect(self.path) as db:
            db.execute(
                "CREATE TABLE dim_exercises (id INTEGER PRIMARY KEY, name TEXT, "
                "description TEXT, instructions TEXT, icon_url TEXT, "
                "anatomy_diagram_url TEXT, media_url TEXT)"
            )
            db.executemany(
                "INSERT INTO dim_exercises VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (1, "Barbell Bench Press", " Description \n", " 1. Setup\n2. Press. ",
                     "database/images/icon/bench-press-1.png",
                     "database/images/anatomy/anatomy_chest.svg",
                     json.dumps(["database/images/media/Press/0.jpg",
                                 "database/images/media/Press/1.jpg"])),
                    (2, "Incline Barbell Bench Press", "Incline", "Press uphill.",
                     None, None, None),
                    (3, "Barbell Back Squat", None, "Squat carefully.", None, None, None),
                ],
            )
        self.client = Mock(spec=GeminiClient)
        self.explainer = ExerciseExplainer(self.client, database_path=self.path)

    def test_single_and_multiple_exercises_use_one_call_per_unique_match(self):
        for names in (
            ["Barbell Bench Press"],
            ["Barbell Back Squat", "barbel bench pres", "Barbell Back Squat"],
        ):
            with self.subTest(names=names):
                self.client.reset_mock()
                expected_names = (
                    ["Barbell Bench Press"] if len(names) == 1
                    else ["Barbell Back Squat", "Barbell Bench Press"]
                )
                self.client.generate.side_effect = [
                    decision(names), *[f" Explain {name} " for name in expected_names]
                ]
                results = self.explainer.handle("Explain my exercises")
                self.assertEqual([item.name for item in results], expected_names)
                self.assertEqual(self.client.generate.call_count, 1 + len(expected_names))
                for result, call in zip(results, self.client.generate.call_args_list[1:]):
                    payload = json.loads(call.args[0])
                    self.assertEqual(payload["query"], "Explain my exercises")
                    self.assertEqual(payload["exercise"]["id"], result.id)
                    self.assertNotIn("llm_explanation", payload["exercise"])
                    self.assertEqual(result.llm_explanation, f"Explain {result.name}")

    def test_database_fields_are_preserved_exactly(self):
        self.client.generate.side_effect = [decision(["Barbell Bench Press"]), "Explanation"]
        result = self.explainer.handle("Explain bench")[0]
        with sqlite3.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            row = dict(db.execute("SELECT * FROM dim_exercises WHERE id = 1").fetchone())
        row["media_urls"] = json.loads(row.pop("media_url"))
        self.assertEqual(result.model_dump(exclude={"llm_explanation"}), row)

    def test_nulls_are_preserved(self):
        self.client.generate.side_effect = [decision(["Barbell Back Squat"]), "Explanation"]
        result = self.explainer.handle("Explain squat")[0]
        for field in ("description", "icon_url", "anatomy_diagram_url", "media_urls"):
            self.assertIsNone(getattr(result, field))

    def test_memory_and_spanish_are_forwarded_to_every_call(self):
        memory = [{"user_query": "Explain bench", "system_response": json.dumps([
            {"name": "Barbell Bench Press", "llm_explanation": "Earlier explanation"}
        ])}]
        self.client.generate.side_effect = [
            decision(["Barbell Bench Press"]), "Explicacion. Pide mas detalles.",
        ]
        result = self.explainer.handle("No entiendo", language="ES", memory=memory)
        self.assertIsInstance(result[0], ExerciseExplanation)
        for call in self.client.generate.call_args_list:
            payload = json.loads(call.args[0])
            self.assertEqual(payload["language"], "ES")
            self.assertEqual(payload["memory"], memory)
            self.assertEqual(payload["query"], "No entiendo")

    def test_missing_names_unknown_names_and_partial_matches_require_clarification(self):
        for names, language in (
            ([], "EN"), (["Unknown zebra exercise"], "EN"),
            (["Barbell Bench Press", "Unknown zebra exercise"], "ES"),
            (["bench press"], "EN"),
        ):
            with self.subTest(names=names, language=language):
                self.client.reset_mock()
                self.client.generate.return_value = decision(names, "" if names else "Which exercise?")
                result = self.explainer.handle("Explain", language=language)
                self.assertIsInstance(result, str)
                self.assertTrue(result)
                if names:
                    self.assertIn(names[-1], result)
                if language == "ES":
                    self.assertIn("Indica", result)
                self.client.generate.assert_called_once()

    def test_invalid_requests_and_decisions(self):
        for query, language in (("", "EN"), (" ", "EN"), (None, "EN"), ("Squat", "FR")):
            with self.subTest(query=query):
                with self.assertRaises(ValueError):
                    self.explainer.handle(query, language=language)
        self.client.generate.assert_not_called()
        for response in (
            "not JSON", "[]", "{}", decision("Squat"), decision([1]),
            decision([" "]), decision([], ""), decision(["Squat"], "Unexpected"),
            '{"exercises": ["Squat"], "message": "", "extra": true}', "", None,
        ):
            with self.subTest(response=response):
                self.client.reset_mock()
                self.client.generate.return_value = response
                with self.assertRaises(ValueError):
                    self.explainer.handle("Explain squat")
                self.client.generate.assert_called_once()

    def test_provider_errors_and_empty_explanations_propagate(self):
        for responses in (
            [RuntimeError("Provider unavailable")],
            [decision(["Barbell Bench Press"]), RuntimeError("Provider unavailable")],
            [decision(["Barbell Bench Press"]), ""],
            [decision(["Barbell Bench Press"]), None],
        ):
            self.client.generate.side_effect = responses
            with self.assertRaises((ValueError, RuntimeError)):
                self.explainer.handle("Explain bench")

    def test_missing_database_is_not_created(self):
        missing = self.path.with_name("missing.db")
        self.client.generate.return_value = decision(["Barbell Bench Press"])
        with self.assertRaises(sqlite3.OperationalError):
            ExerciseExplainer(self.client, database_path=missing).handle("Explain bench")
        self.assertFalse(missing.exists())

    def test_invalid_media_stops_before_explanation(self):
        for media in ("not JSON", '["one"]', '["one", 2]', '"not a list"'):
            with self.subTest(media=media):
                with sqlite3.connect(self.path) as db:
                    db.execute("UPDATE dim_exercises SET media_url = ? WHERE id = 1", (media,))
                self.client.reset_mock()
                self.client.generate.return_value = decision(["Barbell Bench Press"])
                with self.assertRaises(ValueError):
                    self.explainer.handle("Explain bench")
                self.client.generate.assert_called_once()

    def test_fuzzy_threshold_and_ambiguity_margin(self):
        self.assertEqual(normalize_name("Bárbell Bench-Press"), "barbell bench press")
        score = match_score(normalize_name("barbel bench pres"), normalize_name("Barbell Bench Press"))
        self.assertGreaterEqual(score, MIN_MATCH_SCORE)
        first = match_score("bench press", normalize_name("Barbell Bench Press"))
        second = match_score("bench press", normalize_name("Incline Barbell Bench Press"))
        self.assertLess(first - second, MIN_MATCH_MARGIN)
        rows, unresolved = ExerciseCatalog(self.path).resolve(["bench press"])
        self.assertEqual(rows, [])
        self.assertIn("Incline Barbell Bench Press", unresolved[0])

    def test_real_catalog_matching_and_order(self):
        catalog = ExerciseCatalog()
        rows, unresolved = catalog.resolve(["barbel bench pres", "Face Pull", "BARBELL BENCH PRESS"])
        self.assertEqual(unresolved, [])
        self.assertEqual([row["name"] for row in rows], ["Barbell Bench Press", "Face Pull"])
        for name in ("Squat", "Romanian Deadlift", "bench press", "!!!", "unknown zebra fly"):
            rows, unresolved = catalog.resolve([name])
            self.assertEqual(rows, [])
            self.assertEqual(len(unresolved), 1)

    def test_every_catalog_row_is_returned_without_modification(self):
        catalog = ExerciseCatalog()
        with sqlite3.connect(catalog.path) as db:
            db.row_factory = sqlite3.Row
            stored = [dict(row) for row in db.execute(
                "SELECT id, name, description, instructions, icon_url, "
                "anatomy_diagram_url, media_url FROM dim_exercises ORDER BY id"
            )]
        rows, unresolved = catalog.resolve([row["name"] for row in stored])
        self.assertEqual(unresolved, [])
        for row in stored:
            raw = row.pop("media_url")
            row["media_urls"] = json.loads(raw) if raw is not None else None
        self.assertEqual(rows, stored)

    def test_default_client_and_custom_prompts(self):
        with patch("systems.exercise_explainer.ExerciseExplainer.GeminiClient") as factory:
            ExerciseExplainer()
        factory.assert_called_once_with(max_output_tokens=4096)
        path = self.path.with_suffix(".yaml")
        path.write_text("parameters: Extract\nexplanation: Explain\n", encoding="utf-8")
        self.assertEqual(load_prompts(path), {"parameters": "Extract", "explanation": "Explain"})
        self.client.generate.side_effect = [decision(["Barbell Bench Press"]), "Explanation"]
        ExerciseExplainer(self.client, path, database_path=self.path).handle("Explain")
        self.assertEqual(
            [call.kwargs["system_prompt"] for call in self.client.generate.call_args_list],
            ["Extract", "Explain"],
        )
        for content in ("[]", "parameters: Extract", "parameters: ''\nexplanation: x"):
            path.write_text(content, encoding="utf-8")
            with self.assertRaises(ValueError):
                load_prompts(path)
        self.assertEqual(set(load_prompts()), {"parameters", "explanation"})

    def test_generation_and_handler_utilities(self):
        self.client.generate.return_value = " Explanation \n"
        payload = {"query": "Explain", "language": "EN"}
        self.assertEqual(generate(self.client, {"explanation": "Explain"}, "explanation", payload), "Explanation")
        self.client.generate.assert_called_once_with(
            json.dumps(payload, ensure_ascii=True), system_prompt="Explain",
            response_mime_type="text/plain",
        )
        generator = Mock(side_effect=[decision(["Barbell Bench Press"]), "Explanation"])
        results = handle(generator, "Explain", catalog=ExerciseCatalog(self.path))
        self.assertEqual(results[0].llm_explanation, "Explanation")
        self.assertEqual([call.args[0] for call in generator.call_args_list], ["parameters", "explanation"])


if __name__ == "__main__":
    unittest.main()
