"""Resolve extracted exercise names against authoritative SQL catalog records.

Accent/case normalization precedes exact or conservative fuzzy matching. Every
name must resolve before full records are returned, so ambiguity produces a
clarification request rather than explanations for guessed variants.

Attributes:
    DEFAULT_DATABASE (Path): Historical local path exposed by ExerciseCatalog.path;
        None passed to SQLClient still honors provider configuration.
    MIN_MATCH_SCORE (float): Minimum fuzzy score (0.78) for a candidate.
    MIN_MATCH_MARGIN (float): Minimum top-two score gap (0.08) to avoid ambiguity.
"""

import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from obervability.logger import Logger
from sql.SQLClient import SQLClient


DEFAULT_DATABASE = Path(__file__).resolve().parents[5] / "database/gym_app.db"
MIN_MATCH_SCORE = 0.78
MIN_MATCH_MARGIN = 0.08
logger = Logger.get_logger(__name__)


def normalize_name(name: str) -> str:
    """Reduce a name to lowercase ASCII word tokens for catalog comparison.

    Args:
        name (str): Extracted query name or catalog display name.

    Returns:
        str: Space-joined alphanumeric tokens; possibly empty after normalization.
    """
    # 1. Ignore accents and punctuation so formatting does not defeat matching.
    text = unicodedata.normalize("NFKD", name.casefold()).encode("ascii", "ignore").decode("ascii")
    return " ".join(re.findall(r"[a-z0-9]+", text))


def match_score(query: str, candidate: str) -> float:
    """Score normalized names using sequence, token order, and subset evidence.

    Args:
        query (str): Normalized requested name.
        candidate (str): Normalized catalog name.

    Returns:
        float: Best similarity score; subset matches lose 0.06 per extra token.
    """
    # 1. Accept token reordering while retaining character-level similarity.
    query_tokens = query.split()
    candidate_tokens = candidate.split()
    score = max(
        SequenceMatcher(None, query, candidate).ratio(),
        SequenceMatcher(
            None, " ".join(sorted(query_tokens)), " ".join(sorted(candidate_tokens))
        ).ratio(),
    )
    if set(query_tokens).issubset(candidate_tokens):
        # 2. Favor concise subset matches without treating extra variants as exact.
        score = max(score, 1 - 0.06 * (len(candidate_tokens) - len(query_tokens)))
    return score


class ExerciseCatalog:
    """Read authoritative exercise metadata through a per-resolution SQL client.

    Attributes:
        path (Path): Explicit path or historical default path exposed to callers.
        _database_path (str | Path | None): Original override passed to SQLClient;
            None lets SQLClient choose its configured provider/database.
    """

    def __init__(self, database_path: str | Path | None = None) -> None:
        """Record database selection without opening a connection.

        Args:
            database_path (str | Path | None): SQLite override, or provider defaults.

        Returns:
            None: Records database selection without opening a connection.
        """
        # 1. Preserve None for SQLClient's environment-aware provider selection.
        self.path = Path(database_path) if database_path is not None else DEFAULT_DATABASE
        self._database_path = database_path

    @Logger.trace(logger)
    def resolve(self, names: list[str]) -> tuple[list[dict[str, object]], list[str]]:
        """Resolve every name before fetching rows; never guess ambiguous variants.

        Args:
            names (list[str]): Names extracted from the current query/context.

        Returns:
            tuple[list[dict[str, object]], list[str]]: Unique catalog rows in
            requested order and no unresolved names, or no rows and all names
            needing clarification, optionally annotated with up to three matches.

        Raises:
            ValueError: A resolved row disappears or its media list is invalid.
            json.JSONDecodeError: Stored media is not valid JSON.
            Exception: SQL configuration, connection, or query failures propagate.
        """
        # 1. Read only IDs/names while deciding whether all names are trustworthy.
        with SQLClient(database_path=self._database_path) as db:
            catalog = db.fetch_all("SELECT id, name FROM dim_exercises ORDER BY id")
            ids: list[int] = []
            unresolved: list[str] = []
            for name in names:
                normalized = normalize_name(name)
                if not normalized:
                    unresolved.append(name)
                    continue
                # 2. Exact unique matches win; fuzzy matches need score and margin.
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
            # 3. Make clarification atomic: never explain only a guessed subset.
            if unresolved:
                logger.debug("Exercise resolution requires clarification count=%d", len(unresolved))
                return [], unresolved
            # 4. Fetch bound-ID records and normalize media into the response schema.
            exercises: list[dict[str, object]] = []
            for exercise_id in ids:
                row = db.fetch_one(
                    "SELECT id, name, description, instructions, icon_url, "
                    "anatomy_diagram_url, media_url FROM dim_exercises WHERE id = ?",
                    (exercise_id,),
                )
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
            logger.debug("Exercise catalog matches resolved count=%d", len(exercises))
            return exercises, []
