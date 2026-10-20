"""Persist user-owned routine versions through the shared SQL provider boundary.

The repository grounds generated plans in the exercise catalog, validates user
ownership, and stores modern plans plus parameters as JSON routine descriptions.
Confirmed saves serialize writes, deduplicate draft IDs, and activate a new
version without deleting historical routines. Read adapters reconstruct legacy
workout templates only when their descriptions are not modern JSON documents.
No method invokes an LLM; this boundary validates and executes database work
requested by the routine workflow or HTTP dependencies.
"""

import json
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError
from obervability.logger import Logger
from sql.SQLClient import SQLClient, SQLRow

from utils.routinemaker.dataclass.models import (
    LegacyRoutineDay,
    LegacyRoutineExercise,
    LegacyRoutinePlan,
    RoutineParameters,
    RoutinePlan,
)


DEFAULT_DATABASE = Path(__file__).resolve().parents[5] / "database/gym_app.db"
logger = Logger.get_logger(__name__)


class RoutineInputError(ValueError):
    """Signal invalid user scope, confirmation input, or editable routine data.

    This exception adds no state beyond ValueError's message and arguments.
    HTTP callers translate it into a request-validation response.
    """


class RoutineDataError(RuntimeError):
    """Signal stored routine content that cannot satisfy the read contract.

    This exception adds no state beyond RuntimeError's message and arguments.
    Callers distinguish persisted-data failures from user-input errors.
    """


class RoutineRepository:
    """Read catalog data and preserve user-owned routine version history.

    Attributes:
        path (Path | None): Explicit SQLite database path, or None to let
            SQLClient select the configured deployment provider.
    """

    def __init__(self, database_path: str | Path | None = None) -> None:
        """Store an optional database override without opening a connection.

        Args:
            database_path: SQLite path override; None uses provider configuration.

        Returns:
            None: Initializes the repository's path.
        """
        # 1. Defer connection ownership to each repository operation.
        self.path = Path(database_path) if database_path is not None else None

    def _connect(self) -> SQLClient:
        """Create a disconnected provider client for one repository operation.

        Returns:
            SQLClient: Client configured with this repository's optional path.

        Raises:
            ValueError: SQL provider or runtime configuration is invalid.
            OSError: SQL configuration files cannot be read.
        """
        # 1. Reuse the provider boundary rather than coupling repositories to SQLite.
        return SQLClient(database_path=self.path)

    @Logger.trace(logger)
    def validate_user(self, user_id: int | None) -> None:
        """Require a positive integer identifying an existing database user.

        Args:
            user_id: Candidate user identifier; bool and None are rejected.

        Returns:
            None: Confirms the user exists without changing database state.

        Raises:
            RoutineInputError: The identifier is invalid or the user is absent.
            sqlite3.Error: Local database access fails.
            psycopg.Error: Cloud database access fails.
        """
        # 1. Reject invalid scope before executing a parameterized existence check.
        if type(user_id) is not int or user_id < 1:
            raise RoutineInputError("Routine requests require a positive user_id.")
        with self._connect() as db:
            if db.fetch_one("SELECT id FROM dim_users WHERE id = ?", (user_id,)) is None:
                raise RoutineInputError("user_id does not identify an existing database user.")

    @Logger.trace(logger)
    def catalog(self, parameters: RoutineParameters) -> list[dict[str, object]]:
        """Read exercises at or below the requested experience level.

        Args:
            parameters: Collected requirements; an unknown level permits all
                three supported experience tiers.

        Returns:
            list[dict[str, object]]: Catalog rows in ascending exercise-ID order,
                including name, muscle, pattern, equipment, level, and tracking type.

        Raises:
            ValueError: No exercises match the permitted levels.
            sqlite3.Error: Local catalog access fails.
            psycopg.Error: Cloud catalog access fails.
        """
        # 1. Bound agent choices to exercises appropriate for the user's experience.
        levels = ("beginner", "intermediate", "advanced")
        allowed = levels[:levels.index(parameters.level) + 1] if parameters.level else levels
        with self._connect() as db:
            rows = db.fetch_all(
                "SELECT id, name, primary_muscle, pattern, equipment, level, tracking_type "
                "FROM dim_exercises WHERE level IN (" + ",".join("?" for _ in allowed) + ") ORDER BY id",
                allowed,
            )
        if not rows:
            raise ValueError("No catalog exercises match the requested level.")
        return [dict(row) for row in rows]

    @Logger.trace(logger)
    def routines(self, user_id: int) -> list[dict[str, object]]:
        """List a user's saved routine identities for agent-assisted selection.

        Args:
            user_id: User scope used in the query; not independently validated.

        Returns:
            list[dict[str, object]]: ID, name, and active flag, newest ID first.

        Raises:
            sqlite3.Error: Local routine lookup fails.
            psycopg.Error: Cloud routine lookup fails.
        """
        # 1. Return selection metadata rather than placing every saved plan in context.
        with self._connect() as db:
            return db.fetch_all(
                "SELECT id, name, is_active FROM dim_routines WHERE user_id = ? ORDER BY id DESC",
                (user_id,),
            )

    def active_routine(self, user_id: int) -> RoutinePlan | LegacyRoutinePlan | None:
        """Read the active plan without exposing its storage identifier.

        Args:
            user_id: Existing database user identifier.

        Returns:
            RoutinePlan | LegacyRoutinePlan | None: Modern plan, reconstructed
                legacy templates, or None when no usable active routine exists.

        Raises:
            RoutineInputError: The user identifier is invalid or absent.
            RoutineDataError: The active modern document is malformed.
            sqlite3.Error: Local reads fail.
            psycopg.Error: Cloud reads fail.
        """
        # 1. Share modern-versus-legacy resolution with record-based consumers.
        record = self.active_routine_record(user_id)
        return record[1] if record is not None else None

    @Logger.trace(logger)
    def active_routine_record(self, user_id: int) -> tuple[int, RoutinePlan | LegacyRoutinePlan] | None:
        """Resolve the active routine identity and its supported plan format.

        Args:
            user_id: Existing database user identifier.

        Returns:
            tuple[int, RoutinePlan | LegacyRoutinePlan] | None: Latest active
                modern version or reconstructed legacy templates and their
                selected identifier; None when no usable active record exists.

        Raises:
            RoutineInputError: User validation fails.
            RoutineDataError: A modern JSON description is malformed or invalid.
            sqlite3.Error: Local reads fail.
            psycopg.Error: Cloud reads fail.
        """
        # 1. Validate user scope before resolving the latest active record.
        self.validate_user(user_id)
        with self._connect() as db:
            row = db.fetch_one(
                "SELECT id, name, description FROM dim_routines "
                "WHERE user_id = ? AND is_active = 1 ORDER BY id DESC LIMIT 1",
                (user_id,),
            )
        if row is None:
            logger.debug("No active routine found")
            return None
        # 2. Permit legacy fallback only for non-JSON descriptions, not broken JSON.
        try:
            description = row["description"]
            try:
                stored = json.loads(description)
            except (json.JSONDecodeError, TypeError):
                if description is None or (
                    isinstance(description, str) and not description.lstrip().startswith(("{", "["))
                ):
                    logger.debug("Loading active routine from legacy workout templates")
                    return self._legacy_active_routine(user_id)
                raise
            routine = RoutinePlan.model_validate(stored["routine"])
        except (json.JSONDecodeError, TypeError, KeyError, ValidationError) as error:
            raise RoutineDataError(
                f"Active routine {row['id']} contains legacy or invalid data; "
                "save a new routine before loading it."
            ) from error
        return row["id"], routine

    def _legacy_active_routine(self, user_id: int) -> tuple[int, LegacyRoutinePlan] | None:
        """Reconstruct active legacy templates from unlogged workout-set rows.

        Args:
            user_id: User scope already validated by the public read path.

        Returns:
            tuple[int, LegacyRoutinePlan] | None: Last included template ID
                and combined plan, or None when no template sets are available.

        Raises:
            ValidationError: Stored template metrics violate legacy model fields.
            sqlite3.Error: Local template reads fail.
            psycopg.Error: Cloud template reads fail.
        """
        # 1. Exclude logged workouts, empty drafts, and modern JSON descriptions.
        with self._connect() as db:
            rows = db.fetch_all(
                "SELECT r.id AS routine_id, r.name AS routine_name, r.description, "
                "f.exercise_id, f.exercise_order, f.set_number, f.reps, f.weight, "
                "f.duration_seconds, f.distance_meters, e.name AS exercise_name "
                "FROM dim_routines r JOIN fact_workout_sets f "
                "ON f.routine_id = r.id AND f.user_id = r.user_id "
                "JOIN dim_exercises e ON e.id = f.exercise_id "
                "WHERE r.user_id = ? AND r.is_active = 1 AND f.training_id IS NULL "
                "AND substr(ltrim(coalesce(r.description, '')), 1, 1) NOT IN ('{', '[') "
                "ORDER BY r.id, f.exercise_order, f.set_number, f.id",
                (user_id,),
            )
        # 2. Group sets by source routine and exercise without inventing missing metrics.
        days: list[LegacyRoutineDay] = []
        routine_sets: dict[int, list[SQLRow]] = {}
        for row in rows:
            try:
                json.loads(row["description"])
            except (json.JSONDecodeError, TypeError):
                pass
            else:
                continue
            routine_sets.setdefault(row["routine_id"], []).append(row)
        for routine_id, sets in routine_sets.items():
            exercises: list[LegacyRoutineExercise] = []
            exercise_sets: dict[tuple[int, int], list[SQLRow]] = {}
            for item in sets:
                exercise_sets.setdefault((item["exercise_order"], item["exercise_id"]), []).append(item)
            for (_, exercise_id), targets in exercise_sets.items():
                reps = list(dict.fromkeys(str(item["reps"]) for item in targets if item["reps"] is not None))
                notes = []
                for item in targets:
                    metrics = ", ".join(
                        f"{field}={item[field]}"
                        for field in ("reps", "weight", "duration_seconds", "distance_meters")
                        if item[field] is not None
                    )
                    notes.append(f"Set {item['set_number']}: {metrics or 'targets not recorded'}")
                exercises.append(LegacyRoutineExercise(
                    exercise_id=exercise_id, name=targets[0]["exercise_name"],
                    sets=len(targets), reps=" / ".join(reps) or "Not recorded",
                    notes="; ".join(notes),
                ))
            first = sets[0]
            days.append(LegacyRoutineDay(
                day=len(days) + 1, routine_id=routine_id,
                day_type=first["routine_name"],
                info=first["description"] or first["routine_name"],
                exercises=exercises,
            ))
        # 3. Return explicit absent timing/recovery guidance in the legacy display model.
        if not days:
            return None
        return days[-1].routine_id, LegacyRoutinePlan(
            name="Saved workout templates",
            summary="Active workout templates. Empty drafts are excluded.",
            recovery="Recovery guidance not recorded.",
            days=days,
        )

    @Logger.trace(logger)
    def load(self, user_id: int, routine_id: int) -> tuple[RoutinePlan, RoutineParameters]:
        """Load an editable modern plan and its stored requirements.

        Args:
            user_id: Owner required by the parameterized lookup.
            routine_id: Saved routine identifier to edit or validate as a source.

        Returns:
            tuple[RoutinePlan, RoutineParameters]: Validated stored plan and
                generation requirements.

        Raises:
            RoutineInputError: The routine is not user-owned or its document
                is legacy, malformed, or incompatible with the models.
            sqlite3.Error: Local reads fail.
            psycopg.Error: Cloud reads fail.
        """
        # 1. Enforce ownership in the lookup rather than trusting an LLM-selected ID.
        with self._connect() as db:
            row = db.fetch_one(
                "SELECT description FROM dim_routines WHERE id = ? AND user_id = ?",
                (routine_id, user_id),
            )
        if row is None:
            raise RoutineInputError("The selected routine does not belong to this user.")
        try:
            stored = json.loads(row["description"])
            return RoutinePlan.model_validate(stored["routine"]), RoutineParameters.model_validate(stored["parameters"])
        except (json.JSONDecodeError, TypeError, KeyError, ValidationError) as error:
            raise RoutineInputError(
                "The selected routine has legacy or invalid plan data. "
                "Create a new routine to supply complete timing and recovery guidance."
            ) from error

    @Logger.trace(logger)
    def validate_plan(self, plan: RoutinePlan, parameters: RoutineParameters) -> None:
        """Validate a plan against user requirements and the current catalog.

        Args:
            plan: Candidate plan to check.
            parameters: Required day count, session time, and experience level.

        Returns:
            None: Accepts the plan and normalizes exercise names via validation.

        Raises:
            ValidationError: Plan guardrails reject the candidate.
            ValueError: No matching catalog exercises exist.
            sqlite3.Error: Local catalog reads fail.
            psycopg.Error: Cloud catalog reads fail.
        """
        # 1. Revalidate at persistence time even if the preview was validated earlier.
        RoutinePlan.model_validate(
            plan, context={"parameters": parameters, "catalog": self.catalog(parameters)},
        )

    def set_active_routine(self, user_id: int, plan: RoutinePlan) -> int:
        """Save an explicitly supplied plan as a new active version.

        Args:
            user_id: Existing database user receiving the plan.
            plan: Modern plan with timing guidance for each training day.

        Returns:
            int: New active routine version identifier.

        Raises:
            RoutineInputError: The target user is invalid.
            ValueError: Plan or catalog validation fails.
            RuntimeError: The database does not return a valid version identifier.
            sqlite3.Error: Local reads or writes fail.
            psycopg.Error: Cloud reads or writes fail.
        """
        # 1. Derive persistence constraints from the submitted plan's schedule.
        parameters = RoutineParameters(
            days_per_week=len(plan.days),
            hours_per_session=max(day.duration_minutes for day in plan.days) / 60,
        )
        # 2. Allocate a distinct draft identity for this direct plan replacement.
        return self.save(user_id, plan, parameters, str(uuid4()), None)

    @Logger.trace(logger)
    def save(
        self, user_id: int, plan: RoutinePlan, parameters: RoutineParameters,
        draft_id: str, source_routine_id: int | None,
    ) -> int:
        """Persist a confirmed draft idempotently as a user-owned active version.

        Args:
            user_id: Existing positive database user identifier.
            plan: Candidate modern plan validated before writing.
            parameters: Collected requirements stored alongside the plan.
            draft_id: Per-user idempotency key identifying the confirmed preview.
            source_routine_id: Optional user-owned modern version being edited.

        Returns:
            int: Existing version ID for the same draft, without reactivation,
                or newly inserted active version ID.

        Raises:
            RoutineInputError: User or source-routine ownership is invalid.
            ValueError: Plan validation or catalog lookup fails.
            RoutineDataError: An idempotently matched version has an invalid ID.
            RuntimeError: An insert returns no valid version identifier.
            sqlite3.Error: Local transaction operations fail.
            psycopg.Error: Cloud transaction operations fail.
        """
        # 1. Validate user, plan, and source ownership before entering the write lock.
        self.validate_user(user_id)
        self.validate_plan(plan, parameters)
        if source_routine_id is not None:
            self.load(user_id, source_routine_id)
        # 2. Keep generation parameters and lineage with the persisted plan document.
        document = json.dumps({
            "draft_id": draft_id, "source_routine_id": source_routine_id,
            "parameters": parameters.model_dump(), "routine": plan.model_dump(),
        })
        # 3. Serialize draft deduplication and active-version changes in one transaction.
        with self._connect() as db:
            db.begin_write()
            for existing in db.fetch_all(
                "SELECT id, description FROM dim_routines WHERE user_id = ?", (user_id,),
            ):
                try:
                    stored = json.loads(existing["description"])
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(stored, dict) and stored.get("draft_id") == draft_id:
                    identifier = existing["id"]
                    if not isinstance(identifier, int):
                        raise RoutineDataError("Saved routine ID is not an integer.")
                    logger.debug("Routine save reused an existing version")
                    return identifier
            # 4. Preserve historical contents while selecting only the new version.
            db.execute("UPDATE dim_routines SET is_active = 0 WHERE user_id = ?", (user_id,))
            row = db.fetch_one(
                "INSERT INTO dim_routines (user_id, name, description, is_active) VALUES (?, ?, ?, 1) RETURNING id",
                (user_id, plan.name, document),
            )
            if row is None or not isinstance(row["id"], int):
                raise RuntimeError("Database did not return the saved routine ID.")
            routine_id = row["id"]
        logger.info("Routine version saved and activated")
        return routine_id
