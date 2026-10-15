"""Environment-configured SQL client with a DB-API provider boundary."""

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
import os
import sqlite3
from types import TracebackType
from typing import Protocol

from dotenv import dotenv_values
from utils.pipeline.progress import report_sql


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"
SQLValue = str | int | float | bytes | None
SQLParameters = Sequence[SQLValue] | Mapping[str, SQLValue]
SQLRow = dict[str, object]


class _Cursor(Protocol):
    @property
    def description(self) -> Sequence[
        tuple[str, object, object, object, object, object, object]
    ] | None: ...

    @property
    def rowcount(self) -> int: ...

    def execute(self, query: str, parameters: SQLParameters) -> object: ...
    def executemany(self, query: str, parameters: Iterable[SQLParameters]) -> object: ...
    def fetchone(self) -> Sequence[object] | None: ...
    def fetchall(self) -> Sequence[Sequence[object]]: ...
    def close(self) -> None: ...


class _Connection(Protocol):
    def cursor(self) -> _Cursor: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...


def _connect_sqlite(database_path: str) -> _Connection:
    if database_path == ":memory:":
        connection = sqlite3.connect(database_path)
    else:
        path = Path(database_path).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        # Do not silently create an empty database after a configuration typo.
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=rw", uri=True)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


class SQLClient:
    """One synchronous connection; use a separate client per thread or request.

    Writes require commit(), or a successful exit from a with block.
    SQL dialects and parameter placeholders remain provider-specific.
    """

    def __init__(
        self,
        *,
        database_type: str | None = None,
        database_path: str | Path | None = None,
    ) -> None:
        settings = (
            dotenv_values(ENV_FILE, interpolate=False) if ENV_FILE.exists() else {}
        )
        selected_type = (
            database_type
            if database_type is not None
            else os.environ.get(
                "SQL_DATABASE_TYPE", settings.get("SQL_DATABASE_TYPE", "sqlite")
            )
        )
        self.database_type = (selected_type or "").strip().lower()
        if self.database_type != "sqlite":
            raise ValueError(
                f"Unsupported SQL_DATABASE_TYPE: {self.database_type!r}. "
                "Currently supported: sqlite."
            )
        selected_path = (
            str(database_path)
            if database_path is not None
            else os.environ.get(
                "SQLITE_DATABASE_PATH",
                settings.get("SQLITE_DATABASE_PATH", "database/gym_app.db"),
            )
        )
        if selected_path is None or not selected_path.strip():
            raise ValueError("SQLITE_DATABASE_PATH must not be empty.")
        self.database_path = selected_path
        self._connection: _Connection | None = None

    def connect(self) -> None:
        """Open the configured database, unless already connected."""
        if self._connection is None:
            # Add future provider connection factories here; query methods use DB-API.
            self._connection = _connect_sqlite(self.database_path)

    def _get_connection(self) -> _Connection:
        if self._connection is None:
            raise RuntimeError("SQL client is not connected. Call connect() or use 'with'.")
        return self._connection

    def execute(self, query: str, parameters: SQLParameters = ()) -> int:
        """Execute one statement and return its affected row count (-1 if unknown)."""
        cursor = self._get_connection().cursor()
        try:
            report_sql(query, self.database_path)
            cursor.execute(query, parameters)
            return cursor.rowcount
        finally:
            cursor.close()

    def executemany(
        self, query: str, parameters: Iterable[SQLParameters]
    ) -> int:
        """Execute one statement for each parameter set without committing."""
        cursor = self._get_connection().cursor()
        try:
            report_sql(query, self.database_path)
            cursor.executemany(query, parameters)
            return cursor.rowcount
        finally:
            cursor.close()

    def fetch_one(self, query: str, parameters: SQLParameters = ()) -> SQLRow | None:
        """Return one row as a column-name mapping, or None when no rows match."""
        cursor = self._get_connection().cursor()
        try:
            report_sql(query, self.database_path)
            cursor.execute(query, parameters)
            columns = self._column_names(cursor)
            row = cursor.fetchone()
            return dict(zip(columns, row)) if row is not None else None
        finally:
            cursor.close()

    def fetch_all(self, query: str, parameters: SQLParameters = ()) -> list[SQLRow]:
        """Return all rows as column-name mappings."""
        cursor = self._get_connection().cursor()
        try:
            report_sql(query, self.database_path)
            cursor.execute(query, parameters)
            columns = self._column_names(cursor)
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            cursor.close()

    @staticmethod
    def _column_names(cursor: _Cursor) -> list[str]:
        if cursor.description is None:
            raise ValueError("Fetch methods require a statement that returns rows.")
        return [column[0] for column in cursor.description]

    def commit(self) -> None:
        self._get_connection().commit()

    def rollback(self) -> None:
        self._get_connection().rollback()

    def close(self) -> None:
        """Close the connection, discarding any uncommitted changes."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self) -> "SQLClient":
        if self._connection is not None:
            raise RuntimeError("Use a disconnected SQL client to start a with block.")
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()
