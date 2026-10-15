"""Observe direct SQLite connection calls without expanding SQL parameters."""

import sqlite3

from utils.pipeline.progress import report_sql


class ProgressConnection(sqlite3.Connection):
    progress_source: str = "SQLite"

    def execute(self, sql, parameters=(), /):
        report_sql(sql, self.progress_source)
        return super().execute(sql, parameters)

    def executemany(self, sql, parameters, /):
        report_sql(sql, self.progress_source)
        return super().executemany(sql, parameters)
