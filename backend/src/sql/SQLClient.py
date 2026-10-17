"""Environment-configured SQL client with a DB-API provider boundary."""

from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from pathlib import Path
import os
import re
import sqlite3
from types import TracebackType
from urllib.parse import parse_qs, urlsplit

from dotenv import dotenv_values
import psycopg
from config.runtime import runtime_mode
from utils.pipeline.progress import report_sql


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"
SQLValue = str | int | float | bytes | None
SQLParameters = Sequence[SQLValue] | Mapping[str, SQLValue]
SQLRow = dict[str, object]


_Cursor = sqlite3.Cursor | psycopg.Cursor
_Connection = sqlite3.Connection | psycopg.Connection
_SQL_TOKENS = re.compile(
    r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|--[^\n]*|/\*.*?\*/"
    r"|(?P<dollar>\$(?:[A-Za-z_]\w*)?\$).*?(?P=dollar)"
    r"|(?P<positional>\?)|(?<!:):(?P<named>[A-Za-z_]\w*)",
    re.DOTALL,
)


def postgres_query(query: str) -> str:
    """Bind portable placeholders without rewriting SQL literals or comments."""
    if not any(
        match.group("positional") or match.group("named")
        for match in _SQL_TOKENS.finditer(query)
    ):
        return query

    def replace(match: re.Match[str]) -> str:
        if match.group("positional"):
            return "%s"
        if name := match.group("named"):
            return f"%({name})s"
        return match.group()

    return _SQL_TOKENS.sub(replace, query.replace("%", "%%"))


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
    Supports SQLite-style ? and :name parameter binding in either provider.
    """

    def __init__(
        self,
        *,
        database_type: str | None = None,
        database_path: str | Path | None = None,
        database_url: str | None = None,
    ) -> None:
        settings = (
            dotenv_values(ENV_FILE, interpolate=False) if ENV_FILE.exists() else {}
        )
        mode = runtime_mode(settings)
        if database_type is not None:
            selected_type = database_type
        elif database_path is not None:
            selected_type = "sqlite"
        elif mode == "CLOUD":
            selected_type = "postgresql"
        else:
            selected_type = os.environ.get(
                "SQL_DATABASE_TYPE", settings.get("SQL_DATABASE_TYPE", "sqlite")
            )
        self.database_type = (selected_type or "").strip().lower()
        if self.database_type not in ("sqlite", "postgresql"):
            raise ValueError(
                f"Unsupported SQL_DATABASE_TYPE: {self.database_type!r}. "
                "Currently supported: sqlite, postgresql."
            )
        self._database_url: str | None = None
        self._connection: _Connection | None = None
        if self.database_type == "postgresql":
            uri = database_url if database_url is not None else os.environ.get(
                "DATABASE_URL", settings.get("DATABASE_URL", "")
            )
            try:
                parsed = urlsplit(uri or "")
                valid = (
                    parsed.scheme in ("postgres", "postgresql") and parsed.hostname
                    and parsed.username and parsed.password and parsed.path not in ("", "/")
                    and parse_qs(parsed.query).get("sslmode") in (
                        ["require"], ["verify-ca"], ["verify-full"],
                    )
                )
            except ValueError:
                valid = False
            if not valid:
                raise ValueError(
                    "Cloud database requires DATABASE_URL with PostgreSQL credentials, "
                    "a database name, and sslmode=require or stronger."
                )
            self._database_url = uri
            self.database_path = parsed.path.lstrip("/")
            return
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

    def connect(self) -> None:
        """Open the configured database, unless already connected."""
        if self._connection is None:
            if self.database_type == "postgresql":
                if self._database_url is None:
                    raise RuntimeError("PostgreSQL connection URL is not configured.")
                self._connection = psycopg.connect(
                    self._database_url, connect_timeout=10, prepare_threshold=None,
                )
            else:
                self._connection = _connect_sqlite(self.database_path)

    def begin_write(self) -> None:
        """Serialize multi-statement writes, matching SQLite BEGIN IMMEDIATE."""
        if self.database_type == "postgresql":
            self.execute("SELECT pg_advisory_xact_lock(724183970316)")
        else:
            self.execute("BEGIN IMMEDIATE")

    def _query(self, query: str) -> str:
        return postgres_query(query) if self.database_type == "postgresql" else query

    def _report(self, query: str) -> None:
        report_sql(query, self.database_path, database_type=self.database_type)

    def _execute(self, cursor: _Cursor, query: str, parameters: SQLParameters) -> None:
        self._report(query)
        if isinstance(cursor, psycopg.Cursor):
            cursor.execute(self._query(query), parameters or None)
        else:
            cursor.execute(query, parameters)

    def _get_connection(self) -> _Connection:
        if self._connection is None:
            raise RuntimeError("SQL client is not connected. Call connect() or use 'with'.")
        return self._connection

    def execute(self, query: str, parameters: SQLParameters = ()) -> int:
        """Execute one statement and return its affected row count (-1 if unknown)."""
        cursor = self._get_connection().cursor()
        try:
            self._execute(cursor, query, parameters)
            return cursor.rowcount
        finally:
            cursor.close()

    def executemany(
        self, query: str, parameters: Iterable[SQLParameters]
    ) -> int:
        """Execute one statement for each parameter set without committing."""
        cursor = self._get_connection().cursor()
        try:
            self._report(query)
            cursor.executemany(self._query(query), parameters)
            return cursor.rowcount
        finally:
            cursor.close()

    def fetch_one(self, query: str, parameters: SQLParameters = ()) -> SQLRow | None:
        """Return one row as a column-name mapping, or None when no rows match."""
        cursor = self._get_connection().cursor()
        try:
            self._execute(cursor, query, parameters)
            columns = self._column_names(cursor)
            row = cursor.fetchone()
            return self._row(columns, row) if row is not None else None
        finally:
            cursor.close()

    def fetch_all(self, query: str, parameters: SQLParameters = ()) -> list[SQLRow]:
        """Return all rows as column-name mappings."""
        cursor = self._get_connection().cursor()
        try:
            self._execute(cursor, query, parameters)
            columns = self._column_names(cursor)
            return [self._row(columns, row) for row in cursor.fetchall()]
        finally:
            cursor.close()

    @staticmethod
    def _row(columns: list[str], row: Sequence[object]) -> SQLRow:
        return {
            name: value.isoformat() if isinstance(value, date) else value
            for name, value in zip(columns, row)
        }

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
