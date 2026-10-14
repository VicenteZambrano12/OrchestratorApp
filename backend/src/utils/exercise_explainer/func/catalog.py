import json
import re
import sqlite3
import unicodedata
from contextlib import closing
from difflib import SequenceMatcher
from pathlib import Path


DEFAULT_DATABASE = Path(__file__).resolve().parents[5] / "database/gym_app.db"
MIN_MATCH_SCORE = 0.78
MIN_MATCH_MARGIN = 0.08


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name.casefold()).encode("ascii", "ignore").decode("ascii")
    return " ".join(re.findall(r"[a-z0-9]+", text))


def match_score(query: str, candidate: str) -> float:
    query_tokens = query.split()
    candidate_tokens = candidate.split()
    score = max(
        SequenceMatcher(None, query, candidate).ratio(),
        SequenceMatcher(
            None, " ".join(sorted(query_tokens)), " ".join(sorted(candidate_tokens))
        ).ratio(),
    )
    if set(query_tokens).issubset(candidate_tokens):
        score = max(score, 1 - 0.06 * (len(candidate_tokens) - len(query_tokens)))
    return score


class ExerciseCatalog:
    def __init__(self, database_path: str | Path | None = None) -> None:
        self.path = Path(database_path) if database_path is not None else DEFAULT_DATABASE

    def resolve(self, names: list[str]) -> tuple[list[dict[str, object]], list[str]]:
        """Resolve every name before fetching full rows; never guess ambiguous variants."""
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            catalog = db.execute("SELECT id, name FROM dim_exercises ORDER BY id").fetchall()
            ids: list[int] = []
            unresolved: list[str] = []
            for name in names:
                normalized = normalize_name(name)
                if not normalized:
                    unresolved.append(name)
                    continue
                ranked = sorted(
                    (
                        (match_score(normalized, normalize_name(row["name"])), row)
                        for row in catalog
                    ),
                    key=lambda item: item[0],
                    reverse=True,
                )
                exact = [row for row in catalog if normalize_name(row["name"]) == normalized]
                if len(exact) == 1:
                    exercise_id = exact[0]["id"]
                elif (
                    not ranked
                    or ranked[0][0] < MIN_MATCH_SCORE
                    or (
                        len(ranked) > 1
                        and ranked[0][0] - ranked[1][0] < MIN_MATCH_MARGIN
                    )
                ):
                    suggestions = [row["name"] for score, row in ranked[:3] if score >= MIN_MATCH_SCORE]
                    unresolved.append(
                        f"{name} ({' / '.join(suggestions)})" if suggestions else name
                    )
                    continue
                else:
                    exercise_id = ranked[0][1]["id"]
                if exercise_id not in ids:
                    ids.append(exercise_id)
            if unresolved:
                return [], unresolved
            exercises: list[dict[str, object]] = []
            for exercise_id in ids:
                row = db.execute(
                    "SELECT id, name, description, instructions, icon_url, "
                    "anatomy_diagram_url, media_url FROM dim_exercises WHERE id = ?",
                    (exercise_id,),
                ).fetchone()
                if row is None:
                    raise ValueError(f"Exercise {exercise_id} disappeared from the catalog")
                exercise = dict(row)
                raw_media = exercise.pop("media_url")
                media = json.loads(raw_media) if raw_media is not None else None
                if media is not None and (
                    not isinstance(media, list)
                    or len(media) != 2
                    or any(not isinstance(url, str) or not url for url in media)
                ):
                    raise ValueError(f"Exercise {exercise_id} must have exactly two media paths")
                exercise["media_urls"] = media
                exercises.append(exercise)
            return exercises, []
