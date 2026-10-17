import importlib
import os
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from sql.SQLClient import PROJECT_ROOT, SQLClient


MODULE = importlib.import_module("sql.SQLClient")


class SQLClientTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.database = self.directory / "test.db"
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT UNIQUE)")
        self.env_file = self.directory / ".env"
        env_patch = patch.dict(os.environ, {}, clear=True)
        env_patch.start()
        self.addCleanup(env_patch.stop)
        file_patch = patch.object(MODULE, "ENV_FILE", self.env_file)
        file_patch.start()
        self.addCleanup(file_patch.stop)

    def client(self, **kwargs):
        return SQLClient(database_path=self.database, **kwargs)

    def test_default_configuration(self):
        client = SQLClient()
        self.assertEqual(client.database_type, "sqlite")
        self.assertEqual(client.database_path, "database/gym_app.db")
        self.assertEqual(PROJECT_ROOT, Path(__file__).resolve().parents[2])

    def test_dotenv_and_configuration_precedence(self):
        self.env_file.write_text(
            f'SQL_DATABASE_TYPE=" SQLite "\nSQLITE_DATABASE_PATH={self.database}\n',
            encoding="utf-8",
        )
        with SQLClient() as client:
            self.assertEqual(client.fetch_all("SELECT * FROM items"), [])
        with patch.dict(os.environ, {"SQL_DATABASE_TYPE": "postgresql"}):
            with self.assertRaisesRegex(ValueError, "Unsupported SQL_DATABASE_TYPE"):
                SQLClient()
            self.assertEqual(self.client(database_type="sqlite").database_type, "sqlite")
        with patch.dict(os.environ, {"SQLITE_DATABASE_PATH": ":memory:"}):
            self.assertEqual(SQLClient().database_path, ":memory:")
            self.assertEqual(self.client().database_path, str(self.database))

    def test_invalid_configuration(self):
        for provider in ("", "mysql", "postgresql"):
            with self.subTest(provider=provider):
                with self.assertRaisesRegex(ValueError, "SQL_DATABASE_TYPE"):
                    self.client(database_type=provider)
        for setting in ("SQL_DATABASE_TYPE", "SQLITE_DATABASE_PATH"):
            self.env_file.write_text(f"{setting}=\n", encoding="utf-8")
            with self.subTest(setting=setting), self.assertRaisesRegex(ValueError, setting):
                SQLClient()
        with self.assertRaisesRegex(ValueError, "SQLITE_DATABASE_PATH"):
            SQLClient(database_path=" ")

    def test_parameterized_queries_and_committed_writes(self):
        name = "Robert'); DROP TABLE items; --"
        with self.client() as client:
            self.assertEqual(client.execute("INSERT INTO items (name) VALUES (?)", (name,)), 1)
            self.assertEqual(
                client.executemany(
                    "INSERT INTO items (name) VALUES (:name)",
                    ({"name": item} for item in ("second", "third")),
                ),
                2,
            )
            self.assertEqual(
                client.fetch_one("SELECT name FROM items WHERE name = :name", {"name": name}),
                {"name": name},
            )
            self.assertIsNone(client.fetch_one("SELECT * FROM items WHERE id = ?", (99,)))
        with self.client() as client:
            self.assertEqual(
                client.fetch_all("SELECT id, name FROM items ORDER BY id"),
                [{"id": 1, "name": name}, {"id": 2, "name": "second"}, {"id": 3, "name": "third"}],
            )

    def test_context_rolls_back_failed_batch_and_propagates_error(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.client() as client:
                client.executemany(
                    "INSERT INTO items (name) VALUES (?)", [("duplicate",), ("duplicate",)]
                )
        with self.client() as client:
            self.assertEqual(client.fetch_all("SELECT * FROM items"), [])

    def test_context_rolls_back_application_errors(self):
        client = self.client()
        with self.assertRaisesRegex(RuntimeError, "application failed"):
            with client:
                client.execute("INSERT INTO items (name) VALUES ('discarded')")
                raise RuntimeError("application failed")
        with client:
            self.assertEqual(client.fetch_all("SELECT * FROM items"), [])

    def test_commit_failure_closes_connection_and_discards_changes(self):
        client = self.client()
        with self.assertRaises(sqlite3.IntegrityError):
            with client:
                client.execute(
                    "CREATE TABLE children (parent_id INTEGER REFERENCES items(id) "
                    "DEFERRABLE INITIALLY DEFERRED)"
                )
                client.execute("INSERT INTO children VALUES (999)")
        with self.assertRaisesRegex(RuntimeError, "not connected"):
            client.fetch_all("SELECT * FROM children")
        with client:
            self.assertEqual(client.fetch_all("SELECT * FROM children"), [])

    def test_manual_commit_rollback_and_close(self):
        client = self.client()
        self.addCleanup(client.close)
        client.connect()
        client.execute("INSERT INTO items (name) VALUES (?)", ("kept",))
        client.connect()
        client.commit()
        client.execute("UPDATE items SET name = ?", ("rolled back",))
        client.rollback()
        self.assertEqual(client.fetch_one("SELECT name FROM items"), {"name": "kept"})
        client.execute("UPDATE items SET name = ?", ("discarded",))
        client.close()
        client.close()
        client.connect()
        self.assertEqual(client.fetch_one("SELECT name FROM items"), {"name": "kept"})

    def test_disconnected_operations_fail(self):
        client = self.client()
        for operation in (
            lambda: client.execute("SELECT 1"),
            lambda: client.executemany("SELECT ?", []),
            lambda: client.fetch_one("SELECT 1"),
            lambda: client.fetch_all("SELECT 1"),
            client.commit,
            client.rollback,
        ):
            with self.assertRaisesRegex(RuntimeError, "not connected"):
                operation()

    def test_nested_context_is_rejected_without_losing_outer_transaction(self):
        with self.client() as client:
            client.execute("INSERT INTO items (name) VALUES ('kept')")
            with self.assertRaisesRegex(RuntimeError, "disconnected"):
                with client:
                    pass
            self.assertEqual(client.fetch_one("SELECT name FROM items"), {"name": "kept"})
        with self.assertRaisesRegex(RuntimeError, "not connected"):
            client.fetch_all("SELECT * FROM items")

    def test_query_errors_propagate_and_client_can_reconnect(self):
        client = self.client()
        with self.assertRaises(sqlite3.OperationalError):
            with client:
                client.execute("SELECT * FROM missing_table")
        with client:
            self.assertEqual(client.fetch_one("SELECT 1 AS value"), {"value": 1})

    def test_fetch_requires_result_columns(self):
        for method in ("fetch_one", "fetch_all"):
            with self.subTest(method=method), self.assertRaisesRegex(ValueError, "returns rows"):
                with self.client() as client:
                    getattr(client, method)("INSERT INTO items (name) VALUES ('rolled back')")
        with self.client() as client:
            self.assertEqual(client.fetch_all("SELECT * FROM items"), [])

    def test_foreign_keys_are_enforced(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.client() as client:
                client.execute(
                    "CREATE TABLE children (parent_id INTEGER REFERENCES items(id))"
                )
                client.execute("INSERT INTO children VALUES (999)")

    def test_memory_database(self):
        with SQLClient(database_path=":memory:") as client:
            client.execute("CREATE TABLE data (value TEXT)")
            client.execute("INSERT INTO data VALUES (?)", ("hello",))
            self.assertEqual(client.fetch_all("SELECT * FROM data"), [{"value": "hello"}])

    def test_relative_paths_resolve_from_repository_not_cwd(self):
        with patch.object(MODULE, "PROJECT_ROOT", self.directory):
            with SQLClient(database_path="test.db") as client:
                self.assertEqual(client.fetch_all("SELECT * FROM items"), [])

    def test_missing_database_is_not_created(self):
        missing = self.directory / "missing.db"
        with self.assertRaises(sqlite3.OperationalError):
            SQLClient(database_path=missing).connect()
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
