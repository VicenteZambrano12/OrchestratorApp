"""Provide a shared synchronous SQL boundary for SQLite and PostgreSQL.

Repositories and agent history tools use portable question-mark or named
bindings through this client. Deployment mode and explicit overrides select the
provider; connection creation is deferred until ``connect`` or context entry.
PostgreSQL bindings are translated without rewriting literals or comments.

Statement templates are reported to pipeline progress without bound values.
Context-managed operations commit on success, roll back on failure, and close
the connection. Explicitly managed callers own transaction completion. Provider
and configuration errors propagate rather than switching storage backends.
"""

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
from obervability.logger import Logger
from utils.pipeline.progress import report_sql


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"
SQLValue = str | int | float | bytes | None
SQLParameters = Sequence[SQLValue] | Mapping[str, SQLValue]
SQLRow = dict[str, object]
logger = Logger.get_logger(__name__)


_Cursor = sqlite3.Cursor | psycopg.Cursor
_Connection = sqlite3.Connection | psycopg.Connection
_SQL_TOKENS = re.compile(
    r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|--[^\n]*|/\*.*?\*/"
    r"|(?P<dollar>\$(?:[A-Za-z_]\w*)?\$).*?(?P=dollar)"
    r"|(?P<positional>\?)|(?<!:):(?P<named>[A-Za-z_]\w*)",
    re.DOTALL,
)


def postgres_query(query: str) -> str:
    """Translate portable parameter placeholders into psycopg binding syntax.

    Args:
        query: SQL template using ``?`` or ``:name`` placeholders.

    Returns:
        str: PostgreSQL-compatible template. SQL without portable placeholders
            is unchanged; otherwise literal percent signs are escaped.
    """
    # 1. Avoid rewriting statements that need no portable binding translation.
    if not any(
        match.group("positional") or match.group("named")
        for match in _SQL_TOKENS.finditer(query)
    ):
        return query

    def replace(match: re.Match[str]) -> str:
        """Translate a placeholder token while preserving quoted SQL content.

        Args:
            match: Token matched by the SQL-aware placeholder expression.

        Returns:
            str: Psycopg placeholder or the original literal/comment token.
        """
        # 1. Translate only binding tokens, not similarly shaped literal text.
        if match.group("positional"):
            return "%s"
        if name := match.group("named"):
            return f"%({name})s"
        return match.group()

    # 2. Escape percent characters before inserting psycopg placeholders.
    return _SQL_TOKENS.sub(replace, query.replace("%", "%%"))


def _connect_sqlite(database_path: str) -> _Connection:
    """Open SQLite with foreign keys enabled and existing-file protection.

    Args:
        database_path: ``:memory:`` or a filesystem path; relative paths are
            resolved against the project root.

    Returns:
        _Connection: Open SQLite connection with foreign-key enforcement.

    Raises:
        sqlite3.Error: The file is missing, inaccessible, or initialization fails.
    """
    # 1. Allow explicit in-memory databases without creating missing disk files.
    if database_path == ":memory:":
        connection = sqlite3.connect(database_path)
    else:
        path = Path(database_path).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        # 2. Require an existing file so configuration typos cannot create empty stores.
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=rw", uri=True)
    # 3. Enforce relational integrity consistently for repository writes.
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


class SQLClient:
    """One synchronous connection; use a separate client per thread or request.

    Writes require commit(), or a successful exit from a with block.
    Supports SQLite-style ? and :name parameter binding in either provider.

    Attributes:
        database_type (str): Normalized ``sqlite`` or ``postgresql`` provider.
        database_path (str): SQLite path or PostgreSQL database-name label.
        _database_url (str | None): Validated PostgreSQL connection URI.
        _connection (_Connection | None): Lazily opened provider connection.
    """

    def __init__(
        self,
        *,
        database_type: str | None = None,
        database_path: str | Path | None = None,
        database_url: str | None = None,
    ) -> None:
        """Resolve provider configuration without opening a connection.

        Args:
            database_type: Explicit provider override.
            database_path: SQLite path override; selects SQLite when no
                database_type is supplied.
            database_url: PostgreSQL URI override, requiring credentials,
                database name, and ``sslmode=require`` or stronger.

        Returns:
            None: Stores validated connection settings.

        Raises:
            ValueError: Deployment mode, provider, path, or PostgreSQL URI
                configuration is invalid.
            OSError: Existing dotenv settings cannot be read.
        """
        # 1. Resolve deployment mode and explicit provider overrides before defaults.
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
        # 2. Reject unsupported providers instead of silently changing persistence.
        self.database_type = (selected_type or "").strip().lower()
        if self.database_type not in ("sqlite", "postgresql"):
            raise ValueError(
                f"Unsupported SQL_DATABASE_TYPE: {self.database_type!r}. "
                "Currently supported: sqlite, postgresql."
            )
        self._database_url: str | None = None
        self._connection: _Connection | None = None
        # 3. Require a complete TLS-enabled PostgreSQL configuration before use.
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
        # 4. Preserve SQLite path resolution for explicit local/test databases.
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

    @Logger.trace(logger)
    def connect(self) -> None:
        """Open the configured provider connection when not already connected.

        Returns:
            None: Retains one open connection on the instance.

        Raises:
            RuntimeError: PostgreSQL was selected without a configured URL.
            sqlite3.Error: SQLite connection initialization fails.
            psycopg.Error: PostgreSQL connection initialization fails.
        """
        # 1. Reuse the current connection so transaction ownership stays stable.
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
        """Acquire the provider-specific lock for serialized multi-statement writes.

        PostgreSQL uses a transaction-scoped advisory lock shared by this
        application; SQLite uses BEGIN IMMEDIATE.

        Returns:
            None: Starts or participates in the write transaction without commit.

        Raises:
            RuntimeError: The client is disconnected.
            sqlite3.Error: SQLite cannot begin the write transaction.
            psycopg.Error: PostgreSQL cannot acquire the advisory lock.
        """
        # 1. Use provider-specific transaction locking for versioned routine saves.
        if self.database_type == "postgresql":
            self.execute("SELECT pg_advisory_xact_lock(724183970316)")
        else:
            self.execute("BEGIN IMMEDIATE")

    def _query(self, query: str) -> str:
        """Adapt portable bindings for the selected provider.

        Args:
            query: Portable SQL statement template.

        Returns:
            str: Translated PostgreSQL SQL or unchanged SQLite SQL.
        """
        # 1. Keep provider syntax adaptation outside repository code.
        return postgres_query(query) if self.database_type == "postgresql" else query

    def _report(self, query: str) -> None:
        """Emit provider metadata and parameterized SQL progress.

        Args:
            query: Unexpanded SQL template; no parameter values are accepted.

        Returns:
            None: Reports to logging and the active pipeline progress context.
        """
        # 1. Expose execution intent without copying bound user values.
        logger.debug("SQL statement executing provider=%s", self.database_type)
        report_sql(query, self.database_path, database_type=self.database_type)

    def _execute(self, cursor: _Cursor, query: str, parameters: SQLParameters) -> None:
        """Report and execute a statement through a provider cursor.

        Args:
            cursor: Open SQLite or PostgreSQL cursor.
            query: Portable SQL template.
            parameters: Bound positional values or named mapping.

        Returns:
            None: Executes through the supplied cursor without committing.

        Raises:
            sqlite3.Error: SQLite rejects the statement or parameters.
            psycopg.Error: PostgreSQL rejects the statement or parameters.
        """
        # 1. Report the portable template before provider-specific adaptation.
        self._report(query)
        if isinstance(cursor, psycopg.Cursor):
            cursor.execute(self._query(query), parameters or None)
        else:
            cursor.execute(query, parameters)

    def _get_connection(self) -> _Connection:
        """Require an explicitly opened provider connection.

        Returns:
            _Connection: Active instance connection.

        Raises:
            RuntimeError: The client has not connected or has already closed.
        """
        # 1. Prevent hidden connection creation inside transaction operations.
        if self._connection is None:
            raise RuntimeError("SQL client is not connected. Call connect() or use 'with'.")
        return self._connection

    @Logger.trace(logger)
    def execute(self, query: str, parameters: SQLParameters = ()) -> int:
        """Execute one statement without committing its transaction.

        Args:
            query: Portable SQL template.
            parameters: Positional values or named bindings; defaults to none.

        Returns:
            int: Provider row count, or -1 when unknown.

        Raises:
            RuntimeError: The client is disconnected.
            sqlite3.Error: SQLite execution fails.
            psycopg.Error: PostgreSQL execution fails.
        """
        # 1. Keep the cursor local while leaving transaction ownership to the caller.
        cursor = self._get_connection().cursor()
        try:
            self._execute(cursor, query, parameters)
            return cursor.rowcount
        finally:
            cursor.close()

    @Logger.trace(logger)
    def executemany(
        self, query: str, parameters: Iterable[SQLParameters]
    ) -> int:
        """Execute a parameter batch without committing.

        Args:
            query: Portable SQL statement template.
            parameters: Iterable of positional sequences or named mappings.

        Returns:
            int: Provider-reported affected row count, or -1 when unknown.

        Raises:
            RuntimeError: The client is disconnected.
            sqlite3.Error: SQLite batch execution fails.
            psycopg.Error: PostgreSQL batch execution fails.
        """
        # 1. Report the batch template once and close its cursor on every outcome.
        cursor = self._get_connection().cursor()
        try:
            self._report(query)
            cursor.executemany(self._query(query), parameters)
            return cursor.rowcount
        finally:
            cursor.close()

    @Logger.trace(logger)
    def fetch_one(self, query: str, parameters: SQLParameters = ()) -> SQLRow | None:
        """Fetch the first result row as a portable column-name mapping.

        Args:
            query: Portable SQL template expected to return rows.
            parameters: Positional values or named bindings.

        Returns:
            SQLRow | None: First result with date values normalized to ISO text,
                or None when no row matches.

        Raises:
            RuntimeError: The client is disconnected.
            ValueError: The statement produces no result columns.
            sqlite3.Error: SQLite execution or fetching fails.
            psycopg.Error: PostgreSQL execution or fetching fails.
        """
        # 1. Normalize result shape while keeping provider cursor lifetime bounded.
        cursor = self._get_connection().cursor()
        try:
            self._execute(cursor, query, parameters)
            columns = self._column_names(cursor)
            row = cursor.fetchone()
            return self._row(columns, row) if row is not None else None
        finally:
            cursor.close()

    @Logger.trace(logger)
    def fetch_all(self, query: str, parameters: SQLParameters = ()) -> list[SQLRow]:
        """Fetch all result rows as portable column-name mappings.

        Args:
            query: Portable SQL template expected to return rows.
            parameters: Positional values or named bindings.

        Returns:
            list[SQLRow]: Result mappings in query order with ISO date values.

        Raises:
            RuntimeError: The client is disconnected.
            ValueError: The statement produces no result columns.
            sqlite3.Error: SQLite execution or fetching fails.
            psycopg.Error: PostgreSQL execution or fetching fails.
        """
        # 1. Materialize portable rows before releasing the provider cursor.
        cursor = self._get_connection().cursor()
        try:
            self._execute(cursor, query, parameters)
            columns = self._column_names(cursor)
            return [self._row(columns, row) for row in cursor.fetchall()]
        finally:
            cursor.close()

    @staticmethod
    def _row(columns: list[str], row: Sequence[object]) -> SQLRow:
        """Normalize a provider row into the repository result format.

        Args:
            columns: Column names in cursor order.
            row: Values in the same column order.

        Returns:
            SQLRow: Column mapping with date instances represented as ISO strings.
        """
        # 1. Keep date serialization consistent across SQLite and PostgreSQL.
        return {
            name: value.isoformat() if isinstance(value, date) else value
            for name, value in zip(columns, row)
        }

    @staticmethod
    def _column_names(cursor: _Cursor) -> list[str]:
        """Extract column names from a row-producing statement.

        Args:
            cursor: Cursor after SQL execution.

        Returns:
            list[str]: Column names in result order.

        Raises:
            ValueError: The statement does not return rows.
        """
        # 1. Reject write-only statements passed to fetch APIs.
        if cursor.description is None:
            raise ValueError("Fetch methods require a statement that returns rows.")
        return [column[0] for column in cursor.description]

    @Logger.trace(logger)
    def commit(self) -> None:
        """Commit pending writes on the active connection.

        Returns:
            None: Completes the current transaction.

        Raises:
            RuntimeError: The client is disconnected.
            sqlite3.Error: SQLite commit fails.
            psycopg.Error: PostgreSQL commit fails.
        """
        # 1. Delegate durability to the configured provider.
        self._get_connection().commit()

    @Logger.trace(logger)
    def rollback(self) -> None:
        """Discard pending writes on the active connection.

        Returns:
            None: Rolls back the current transaction.

        Raises:
            RuntimeError: The client is disconnected.
            sqlite3.Error: SQLite rollback fails.
            psycopg.Error: PostgreSQL rollback fails.
        """
        # 1. Preserve explicit failure recovery without reconnecting.
        self._get_connection().rollback()

    @Logger.trace(logger)
    def close(self) -> None:
        """Close the connection and discard any uncommitted changes.

        Returns:
            None: Clears the connection reference; safe when already closed.

        Raises:
            sqlite3.Error: SQLite close fails.
            psycopg.Error: PostgreSQL close fails.
        """
        # 1. Release provider resources and restore the disconnected state.
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self) -> "SQLClient":
        """Open a fresh connection for a transaction-scoped context.

        Returns:
            SQLClient: This connected client.

        Raises:
            RuntimeError: A connection is already open or configuration is incomplete.
            sqlite3.Error: SQLite connection fails.
            psycopg.Error: PostgreSQL connection fails.
        """
        # 1. Reject nested ownership of an already-open transaction.
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
        """Complete the context transaction and release its connection.

        Args:
            exc_type: Exception type from the context body, or None on success.
            exc_value: Exception instance supplied by the context manager protocol.
            traceback: Traceback supplied by the context manager protocol.

        Returns:
            None: Does not suppress exceptions from the context body.

        Raises:
            sqlite3.Error: SQLite commit, rollback, or close fails.
            psycopg.Error: PostgreSQL commit, rollback, or close fails.
        """
        # 1. Commit only successful work; always attempt to release the connection.
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()
