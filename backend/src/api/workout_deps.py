import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from api.DataClasses.Workout import WorkoutDay, WorkoutRequest, WorkoutResponse
from utils.routinemaker.func.repository import DEFAULT_DATABASE


class WorkoutRepository:
    def __init__(self, path: Path = DEFAULT_DATABASE):
        self.path = path

    def days(self, user_id: int) -> list[WorkoutDay]:
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=6)
        end = today + timedelta(days=1)
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            if db.execute("SELECT 1 FROM dim_users WHERE id = ?", (user_id,)).fetchone() is None:
                raise HTTPException(status_code=404, detail="The user does not exist.")
            workout_dates = {
                row[0] for row in db.execute(
                    "SELECT DISTINCT date(created_at) FROM fact_workout_sets "
                    "WHERE user_id = ? AND training_id IS NOT NULL "
                    "AND date(created_at) >= ? AND date(created_at) < ?",
                    (user_id, start.isoformat(), end.isoformat()),
                )
            }
        weekdays = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
        dates = [start + timedelta(days=offset) for offset in range(7)]
        return [
            WorkoutDay(
                date=day, day_of_week=weekdays[day.weekday()],
                has_routine=day.isoformat() in workout_dates,
            )
            for day in dates
        ]

    def save(self, user_id: int, workout: WorkoutRequest) -> WorkoutResponse:
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=rw", uri=True)) as db, db:
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM dim_users WHERE id = ?", (user_id,)).fetchone() is None:
                raise HTTPException(status_code=404, detail="The user does not exist.")
            if db.execute(
                "SELECT 1 FROM dim_routines WHERE id = ? AND user_id = ?",
                (workout.routine_id, user_id),
            ).fetchone() is None:
                raise HTTPException(status_code=422, detail="The selected routine does not belong to this user.")
            exercise_ids = {item.exercise_id for item in workout.sets}
            placeholders = ",".join("?" for _ in exercise_ids)
            known_ids = {
                row[0] for row in db.execute(
                    f"SELECT id FROM dim_exercises WHERE id IN ({placeholders})",
                    tuple(exercise_ids),
                )
            }
            if exercise_ids != known_ids:
                raise HTTPException(status_code=422, detail="Workout contains unknown exercise IDs.")

            training_id = str(uuid4())
            created_at = datetime.now(timezone.utc).replace(microsecond=0)
            exercise_order: dict[int, int] = {}
            set_numbers: dict[int, int] = {}
            rows = []
            for item in workout.sets:
                exercise_order.setdefault(item.exercise_id, len(exercise_order) + 1)
                set_numbers[item.exercise_id] = set_numbers.get(item.exercise_id, 0) + 1
                rows.append((
                    user_id, workout.routine_id, item.exercise_id, training_id,
                    exercise_order[item.exercise_id], set_numbers[item.exercise_id],
                    item.reps, item.weight, item.duration_seconds, item.distance_meters,
                    item.rpe, created_at.strftime("%Y-%m-%d %H:%M:%S"),
                ))
            db.executemany(
                "INSERT INTO fact_workout_sets "
                "(user_id, routine_id, exercise_id, training_id, exercise_order, set_number, "
                "reps, weight, duration_seconds, distance_meters, rpe, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        return WorkoutResponse(
            training_id=training_id, user_id=user_id, routine_id=workout.routine_id,
            date=created_at.date(), created_at=created_at, sets_saved=len(rows),
        )


def get_workout_repository() -> WorkoutRepository:
    return WorkoutRepository()
