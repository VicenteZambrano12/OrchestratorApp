"""Bridge direct SQLite connection operations into pipeline progress reporting.

This connection subclass emits parameterized statement templates before direct
``execute`` and ``executemany`` calls. It does not expand bound values, rewrite
queries, or replace SQLite transaction behavior. Reporting is routed through
the workflow progress context used by streaming chat.
"""

import sqlite3

from obervability.logger import Logger
from utils.pipeline.progress import report_sql


logger = Logger.get_logger(__name__)


class ProgressConnection(sqlite3.Connection):
    """Report direct SQLite statements using an associated progress source.

    Attributes:
        progress_source (str): Source label supplied to SQL progress reporting,
            defaulting to ``SQLite``.
    """

    progress_source: str = "SQLite"

    @Logger.trace(logger)
    def execute(self, sql, parameters=(), /):
        """Report and execute one SQLite statement with bound parameters.

        Args:
            sql: SQL statement template accepted by SQLite.
            parameters: Positional sequence or named mapping of bound values.

        Returns:
            sqlite3.Cursor: Cursor returned by the underlying connection.

        Raises:
            sqlite3.Error: SQLite rejects the statement or its bindings.
        """
        # 1. Emit the template separately from sensitive parameter values.
        report_sql(sql, self.progress_source)
        return super().execute(sql, parameters)

    @Logger.trace(logger)
    def executemany(self, sql, parameters, /):
        """Report a statement once and execute it for each parameter set.

        Args:
            sql: SQL statement template accepted by SQLite.
            parameters: Iterable of positional sequences or named mappings.

        Returns:
            sqlite3.Cursor: Cursor returned by the underlying connection.

        Raises:
            sqlite3.Error: SQLite rejects a statement or parameter set.
        """
        # 1. Represent the batch as one SQL progress step without exposing values.
        report_sql(sql, self.progress_source)
        return super().executemany(sql, parameters)
