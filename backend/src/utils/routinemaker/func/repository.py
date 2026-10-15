import json
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError
from sql.progress import ProgressConnection

from utils.routinemaker.dataclass.models import (
    LegacyRoutineDay,
    LegacyRoutineExercise,
    LegacyRoutinePlan,
    RoutineParameters,
    RoutinePlan,
)


DEFAULT_DATABASE = Path(__file__).resolve().parents[5] / "database/gym_app.db"


class RoutineInputError(ValueError):
    """A routine request needs valid user-owned input."""


class RoutineDataError(RuntimeError):
    """A saved routine does not contain a supported routine plan."""


class RoutineRepository:
    def __init__(self, database_path: str | Path | None = None) -> None:
        self.path = Path(database_path) if database_path is not None else DEFAULT_DATABASE

    def _connect(self, *, write: bool = False) -> sqlite3.Connection:
        db = sqlite3.connect(
            self.path.resolve().as_uri() + ("?mode=rw" if write else "?mode=ro"),
            uri=True, factory=ProgressConnection,
        )
        db.progress_source = self.path.name
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def validate_user(self, user_id: int | None) -> None:
        if type(user_id) is not int or user_id < 1:
            raise RoutineInputError("Routine requests require a positive user_id.")
        with closing(self._connect()) as db:
            if db.execute("SELECT id FROM dim_users WHERE id = ?", (user_id,)).fetchone() is None:
                raise RoutineInputError("user_id does not identify an existing database user.")

    def catalog(self, parameters: RoutineParameters) -> list[dict[str, object]]:
        levels = ("beginner", "intermediate", "advanced")
        allowed = levels[:levels.index(parameters.level) + 1] if parameters.level else levels
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT id, name, primary_muscle, pattern, equipment, level, tracking_type "
                "FROM dim_exercises WHERE level IN (" + ",".join("?" for _ in allowed) + ") ORDER BY id",
                allowed,
            ).fetchall()
        if not rows:
            raise ValueError("No catalog exercises match the requested level.")
        return [dict(row) for row in rows]

    def routines(self, user_id: int) -> list[dict[str, object]]:
        with closing(self._connect()) as db:
            return [dict(row) for row in db.execute(
                "SELECT id, name, is_active FROM dim_routines WHERE user_id = ? ORDER BY id DESC",
                (user_id,),
            )]

    def active_routine(self, user_id: int) -> RoutinePlan | LegacyRoutinePlan | None:
        record = self.active_routine_record(user_id)
        return record[1] if record is not None else None

    def active_routine_record(self, user_id: int) -> tuple[int, RoutinePlan | LegacyRoutinePlan] | None:
        self.validate_user(user_id)
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT id, name, description FROM dim_routines "
                "WHERE user_id = ? AND is_active = 1 ORDER BY id DESC LIMIT 1",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            description = row["description"]
            try:
                stored = json.loads(description)
            except (json.JSONDecodeError, TypeError):
                if description is None or (
                    isinstance(description, str) and not description.lstrip().startswith(("{", "["))
                ):
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
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT r.id AS routine_id, r.name AS routine_name, r.description, "
                "f.exercise_id, f.exercise_order, f.set_number, f.reps, f.weight, "
                "f.duration_seconds, f.distance_meters, e.name AS exercise_name "
                "FROM dim_routines r JOIN fact_workout_sets f "
                "ON f.routine_id = r.id AND f.user_id = r.user_id "
                "JOIN dim_exercises e ON e.id = f.exercise_id "
                "WHERE r.user_id = ? AND r.is_active = 1 AND f.training_id IS NULL "
                "AND (r.description IS NULL OR NOT json_valid(r.description)) "
                "AND substr(ltrim(coalesce(r.description, '')), 1, 1) NOT IN ('{', '[') "
                "ORDER BY r.id, f.exercise_order, f.set_number, f.id",
                (user_id,),
            ).fetchall()
        days: list[LegacyRoutineDay] = []
        routine_sets: dict[int, list[sqlite3.Row]] = {}
        for row in rows:
            routine_sets.setdefault(row["routine_id"], []).append(row)
        for routine_id, sets in routine_sets.items():
            exercises: list[LegacyRoutineExercise] = []
            exercise_sets: dict[tuple[int, int], list[sqlite3.Row]] = {}
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
        if not days:
            return None
        return days[-1].routine_id, LegacyRoutinePlan(
            name="Saved workout templates",
            summary="Active workout templates. Empty drafts are excluded.",
            recovery="Recovery guidance not recorded.",
            days=days,
        )

    def load(self, user_id: int, routine_id: int) -> tuple[RoutinePlan, RoutineParameters]:
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT description FROM dim_routines WHERE id = ? AND user_id = ?",
                (routine_id, user_id),
            ).fetchone()
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

    def validate_plan(self, plan: RoutinePlan, parameters: RoutineParameters) -> None:
        RoutinePlan.model_validate(
            plan, context={"parameters": parameters, "catalog": self.catalog(parameters)},
        )

    def set_active_routine(self, user_id: int, plan: RoutinePlan) -> int:
        parameters = RoutineParameters(
            days_per_week=len(plan.days),
            hours_per_session=max(day.duration_minutes for day in plan.days) / 60,
        )
        return self.save(user_id, plan, parameters, str(uuid4()), None)

    def save(
        self, user_id: int, plan: RoutinePlan, parameters: RoutineParameters,
        draft_id: str, source_routine_id: int | None,
    ) -> int:
        self.validate_user(user_id)
        self.validate_plan(plan, parameters)
        if source_routine_id is not None:
            self.load(user_id, source_routine_id)
        document = json.dumps({
            "draft_id": draft_id, "source_routine_id": source_routine_id,
            "parameters": parameters.model_dump(), "routine": plan.model_dump(),
        })
        with closing(self._connect(write=True)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT id FROM dim_routines WHERE user_id = ? "
                "AND json_extract(CASE WHEN json_valid(description) THEN description ELSE '{}' END, '$.draft_id') = ?",
                (user_id, draft_id),
            ).fetchone()
            if existing is not None:
                return existing["id"]
            db.execute("UPDATE dim_routines SET is_active = 0 WHERE user_id = ?", (user_id,))
            cursor = db.execute(
                "INSERT INTO dim_routines (user_id, name, description, is_active) VALUES (?, ?, ?, 1)",
                (user_id, plan.name, document),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("Database did not return the saved routine ID.")
            return cursor.lastrowid
