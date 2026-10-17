import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

DATABASE_PATH = Path(__file__).resolve().parents[3] / "database/gym_app.db"


class UserRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    username: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    weight_unit: Literal["kg", "lbs"] = "kg"


class UserResponse(UserRegistration):
    id: int = Field(gt=0)


class UserRepository:
    def __init__(self, path: Path = DATABASE_PATH):
        self.path = path

    def connect(self):
        db = sqlite3.connect(self.path.resolve().as_uri() + "?mode=rw", uri=True)
        db.row_factory = sqlite3.Row
        return db

    def list_users(self) -> list[UserResponse]:
        with closing(self.connect()) as db, db:
            # Serialize first-use initialization so concurrent visitors share one default.
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO dim_users (username) SELECT 'Jamie Davis' "
                "WHERE NOT EXISTS (SELECT 1 FROM dim_users)"
            )
            return [
                UserResponse(**dict(row))
                for row in db.execute("SELECT id, username, weight_unit FROM dim_users ORDER BY id")
            ]

    def create(self, registration: UserRegistration) -> UserResponse:
        with closing(self.connect()) as db, db:
            try:
                cursor = db.execute(
                    "INSERT INTO dim_users (username, weight_unit) VALUES (?, ?)",
                    (registration.username, registration.weight_unit),
                )
            except sqlite3.IntegrityError as error:
                if db.execute(
                    "SELECT 1 FROM dim_users WHERE username = ?", (registration.username,)
                ).fetchone() is not None:
                    raise HTTPException(status_code=409, detail="That username is already registered.") from error
                raise
            return UserResponse(id=cursor.lastrowid, **registration.model_dump())


def get_user_repository() -> UserRepository:
    return UserRepository()
