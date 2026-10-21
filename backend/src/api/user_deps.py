"""Define local profile schemas and SQL-backed API dependencies.

Profiles are selectable user scopes, not authenticated accounts. Repository
operations use SQLClient's configured backend unless an explicit path is supplied;
listing initializes the default profile only when the users table is empty.
"""

from pathlib import Path
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from obervability.logger import Logger
from sql.SQLClient import SQLClient

DATABASE_PATH = Path(__file__).resolve().parents[3] / "database/gym_app.db"
logger = Logger.get_logger(__name__)


class UserRegistration(BaseModel):
    """Validate the body accepted by profile registration.

    The repository persists these values without password or account creation.
    Unknown fields and coercion are rejected.

    Attributes:
        username (Annotated[str, StringConstraints(strip_whitespace=True,
            min_length=1, max_length=80)]): Trimmed, nonempty profile name of
            at most 80 characters; uniqueness is enforced by the database.
        weight_unit (Literal["kg", "lbs"]): Preferred unit, defaulting to kg.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    username: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    weight_unit: Literal["kg", "lbs"] = "kg"


class UserResponse(UserRegistration):
    """Return a stored profile through listing and registration endpoints.

    Attributes:
        username (Annotated[str, StringConstraints(strip_whitespace=True,
            min_length=1, max_length=80)]): Inherited validated profile name.
        weight_unit (Literal["kg", "lbs"]): Inherited preferred weight unit.
        id (int): Positive database identifier used for user-scoped requests.
    """

    id: int = Field(gt=0)


class UserRepository:
    """Persist and enumerate local profiles through transaction-scoped clients.

    FastAPI's dependency factory creates repository instances; connections are
    opened per operation and profile rows are validated against UserResponse.

    Attributes:
        path (Path | None): Optional database override passed to SQLClient;
            None leaves backend and database selection to runtime configuration.
    """

    def __init__(self, path: Path | None = None):
        """Retain database selection without opening a connection.

        Args:
            path (Path | None): Explicit database path or runtime default.

        Returns:
            None: Retains database selection without opening a SQL connection.
        """
        # 1. Keep repository construction separate from transaction-scoped SQL access.
        self.path = path

    def connect(self) -> SQLClient:
        """Construct a client for the repository's configured database.

        Returns:
            SQLClient: Client to be entered by a repository operation.

        Raises:
            ValueError: If SQLClient rejects runtime database configuration.
        """
        # 1. Apply the repository's database selection to each operation's client.
        return SQLClient(database_path=self.path)

    @Logger.trace(logger)
    def list_users(self) -> list[UserResponse]:
        """List profiles in ID order, initializing the empty database once.

        Returns:
            list[UserResponse]: Validated profiles ordered by ascending ID.

        Raises:
            pydantic.ValidationError: If stored profile data violates the schema.
            Exception: Database/configuration failures propagate from SQLClient.
        """
        # 1. Serialize empty-table initialization with the subsequent profile read.
        with self.connect() as db:
            db.begin_write()
            db.execute(
                "INSERT INTO dim_users (username) SELECT 'Jamie Davis' "
                "WHERE NOT EXISTS (SELECT 1 FROM dim_users)"
            )
            # 2. Validate persistence rows before returning the public API shape.
            users = [
                UserResponse.model_validate(row)
                for row in db.fetch_all("SELECT id, username, weight_unit FROM dim_users ORDER BY id")
            ]
        logger.debug("User profiles loaded count=%d", len(users))
        return users

    @Logger.trace(logger)
    def create(self, registration: UserRegistration) -> UserResponse:
        """Insert a profile without overwriting an existing username.

        Args:
            registration (UserRegistration): Validated name and unit preference.

        Returns:
            UserResponse: Newly persisted profile after transaction completion.

        Raises:
            HTTPException: With status 409 when the username already exists.
            pydantic.ValidationError: If the returned database row is invalid.
            Exception: Database/configuration failures propagate from SQLClient.
        """
        # 1. Let the unique constraint arbitrate concurrent registrations.
        with self.connect() as db:
            row = db.fetch_one(
                "INSERT INTO dim_users (username, weight_unit) VALUES (?, ?) "
                "ON CONFLICT (username) DO NOTHING RETURNING id, username, weight_unit",
                (registration.username, registration.weight_unit),
            )
            # 2. Translate only the duplicate-name outcome into an API conflict.
            if row is None:
                logger.warning("User registration rejected reason=duplicate_username")
                raise HTTPException(status_code=409, detail="That username is already registered.")
            user = UserResponse.model_validate(row)
        logger.info("User profile created")
        return user


def get_user_repository() -> UserRepository:
    """Construct the runtime-configured profile dependency.

    Returns:
        UserRepository: Repository whose operations create their own SQL clients.
    """
    # 1. Inject profile persistence without holding a connection across requests.
    return UserRepository()
