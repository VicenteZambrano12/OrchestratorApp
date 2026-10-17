from pathlib import Path
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sql.SQLClient import SQLClient

DATABASE_PATH = Path(__file__).resolve().parents[3] / "database/gym_app.db"


class UserRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    username: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    weight_unit: Literal["kg", "lbs"] = "kg"


class UserResponse(UserRegistration):
    id: int = Field(gt=0)


class UserRepository:
    def __init__(self, path: Path | None = None):
        self.path = path

    def connect(self) -> SQLClient:
        return SQLClient(database_path=self.path)

    def list_users(self) -> list[UserResponse]:
        with self.connect() as db:
            # Serialize first-use initialization so concurrent visitors share one default.
            db.begin_write()
            db.execute(
                "INSERT INTO dim_users (username) SELECT 'Jamie Davis' "
                "WHERE NOT EXISTS (SELECT 1 FROM dim_users)"
            )
            return [
                UserResponse.model_validate(row)
                for row in db.fetch_all("SELECT id, username, weight_unit FROM dim_users ORDER BY id")
            ]

    def create(self, registration: UserRegistration) -> UserResponse:
        with self.connect() as db:
            row = db.fetch_one(
                "INSERT INTO dim_users (username, weight_unit) VALUES (?, ?) "
                "ON CONFLICT (username) DO NOTHING RETURNING id, username, weight_unit",
                (registration.username, registration.weight_unit),
            )
            if row is None:
                raise HTTPException(status_code=409, detail="That username is already registered.")
            return UserResponse.model_validate(row)


def get_user_repository() -> UserRepository:
    return UserRepository()
