# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["psycopg[binary]>=3.2,<4", "pgserver>=0.1.4,<1"]
# ///
import contextlib
import io
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import pgserver
import psycopg

import migrate_database as migration


class DatabaseMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cluster = tempfile.TemporaryDirectory(prefix="orchestrator-migration-test-")
        cls.server = pgserver.get_server(Path(cls.cluster.name) / "pgdata", cleanup_mode="stop")
        cls.uri = cls.server.get_uri()
        with contextlib.closing(
            sqlite3.connect(migration.SOURCE_DATABASE.as_uri() + "?mode=ro", uri=True)
        ) as original:
            cls.source_ddl = [
                row[0] for row in original.execute(
                    "SELECT sql FROM sqlite_master WHERE type IN ('table', 'index') "
                    "AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL ORDER BY type DESC, name"
                )
            ]

    @classmethod
    def tearDownClass(cls):
        cls.server.cleanup()
        cls.cluster.cleanup()

    def setUp(self):
        self.source = sqlite3.connect(":memory:")
        self.addCleanup(self.source.close)
        self.source.execute("PRAGMA foreign_keys = ON")
        for statement in self.source_ddl:
            self.source.execute(statement)
        self.source.execute(
            "INSERT INTO dim_exercises "
            "(id, name, instructions, primary_muscle, pattern, equipment, mechanic, level, intensity, media_url) "
            "VALUES (12, 'Press', 'Línea 1\\nLine 2', 'chest', 'push', 'barbell', "
            "'compound', 'beginner', 'medium', '[\"database/images/media/press/0.jpg\"]')"
        )
        self.source.execute("INSERT INTO dim_users (id, username) VALUES (7, 'Demo üser')")
        self.source.execute("INSERT INTO dim_routines (id, user_id, name) VALUES (19, 7, 'Demo')")
        self.source.execute(
            "INSERT INTO fact_workout_sets "
            "(id, user_id, routine_id, exercise_id, weight, rpe) VALUES (53, 7, 19, 12, 12.5, 7.5)"
        )
        self.source.execute("UPDATE sqlite_sequence SET seq = 123 WHERE name = 'dim_users'")
        self.source.commit()
        self.target = psycopg.connect(self.uri, autocommit=True)
        self.addCleanup(self.target.close)
        self.target.execute("DROP SCHEMA public CASCADE")
        self.target.execute("CREATE SCHEMA public")

    def populate(self):
        with self.target.transaction():
            return migration.populate(self.source, self.target)

    def test_full_copy_rows_sequences_indexes_and_constraints(self):
        counts = self.populate()
        self.assertEqual(counts, {table: 1 for table in migration.TABLES})
        for table in migration.TABLES:
            expected = self.source.execute(f'SELECT * FROM "{table}" ORDER BY id').fetchall()
            actual = self.target.execute(f'SELECT * FROM public."{table}" ORDER BY id').fetchall()
            self.assertEqual(actual, expected)
        identifier = self.target.execute(
            "INSERT INTO public.dim_users (username) VALUES ('New user') RETURNING id"
        ).fetchone()[0]
        self.assertEqual(identifier, 124)
        indexes = self.target.execute(
            "SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'public' AND indexname LIKE 'idx_%'"
        ).fetchone()[0]
        self.assertEqual(indexes, 6)
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            self.target.execute(
                "INSERT INTO public.dim_routines (user_id, name) VALUES (999999, 'Invalid')"
            )

    def test_nonempty_target_is_preserved(self):
        self.target.execute("CREATE TABLE public.keep_me (value TEXT)")
        self.target.execute("INSERT INTO public.keep_me VALUES ('untouched')")
        with self.assertRaisesRegex(ValueError, "not empty"):
            self.populate()
        self.assertEqual(self.target.execute("SELECT value FROM public.keep_me").fetchall(), [("untouched",)])

    def test_failed_copy_rolls_back_all_tables(self):
        self.source.execute("PRAGMA ignore_check_constraints = ON")
        self.source.execute("UPDATE fact_workout_sets SET rpe = 11")
        self.source.commit()
        # Skip the source integrity check to exercise a failure inside PostgreSQL COPY.
        with patch.object(migration, "validate_source", return_value={table: 1 for table in migration.TABLES}):
            with self.assertRaises(psycopg.errors.CheckViolation):
                self.populate()
        self.assertEqual(
            self.target.execute("SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public'").fetchone()[0],
            0,
        )

    def test_invalid_source_foreign_keys_are_rejected(self):
        self.source.execute("PRAGMA foreign_keys = OFF")
        self.source.execute("UPDATE dim_routines SET user_id = 999")
        self.source.commit()
        with self.assertRaisesRegex(ValueError, "foreign-key"):
            self.populate()

    def test_empty_source_resets_sequences_to_one(self):
        for table in reversed(migration.TABLES):
            self.source.execute(f'DELETE FROM "{table}"')
        self.source.execute("DELETE FROM sqlite_sequence")
        self.source.commit()
        self.assertEqual(self.populate(), {table: 0 for table in migration.TABLES})
        self.assertEqual(
            self.target.execute(
                "INSERT INTO public.dim_users (username) VALUES ('First') RETURNING id"
            ).fetchone()[0],
            1,
        )

    def test_changed_column_layout_rolls_back(self):
        self.source.execute("ALTER TABLE dim_users ADD COLUMN unexpected TEXT")
        with self.assertRaisesRegex(ValueError, "columns differ"):
            self.populate()
        self.assertEqual(
            self.target.execute("SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public'").fetchone()[0],
            0,
        )

    def test_second_import_is_rejected(self):
        self.populate()
        with self.assertRaisesRegex(ValueError, "not empty"):
            self.populate()
        self.assertEqual(self.target.execute("SELECT COUNT(*) FROM public.dim_users").fetchone()[0], 1)

    def test_cli_commits_to_isolated_local_postgres(self):
        with tempfile.TemporaryDirectory(prefix="orchestrator-migration-source-") as directory:
            source_path = Path(directory) / "source.db"
            with contextlib.closing(sqlite3.connect(source_path)) as snapshot:
                self.source.backup(snapshot)
            output = io.StringIO()
            with patch.object(migration, "connection_uri", return_value=self.uri):
                with contextlib.redirect_stdout(output):
                    self.assertEqual(migration.main(["--source", str(source_path)]), 0)
            self.assertIn("Import committed; all copied rows verified.", output.getvalue())
            self.assertEqual(self.target.execute("SELECT COUNT(*) FROM public.fact_workout_sets").fetchone()[0], 1)
            with contextlib.closing(sqlite3.connect(source_path)) as snapshot:
                self.assertEqual(snapshot.execute("SELECT COUNT(*) FROM fact_workout_sets").fetchone()[0], 1)


class MigrationConfigurationTests(unittest.TestCase):
    def test_dry_run_never_connects_to_postgres_or_reads_secrets(self):
        with patch.object(migration, "connection_uri") as uri:
            with patch.object(migration.psycopg, "connect") as connect:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(migration.main(["--dry-run"]), 0)
        uri.assert_not_called()
        connect.assert_not_called()

    def test_tls_is_required(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://demo:placeholder@example.invalid/app"}):
            with self.assertRaisesRegex(ValueError, "sslmode"):
                migration.connection_uri()

    def test_environment_url_avoids_gcloud(self):
        value = "postgresql://demo:placeholder@example.invalid/app?sslmode=require"
        with patch.dict(os.environ, {"DATABASE_URL": value}):
            with patch.object(migration.subprocess, "run") as run:
                self.assertEqual(migration.connection_uri(), value)
        run.assert_not_called()

    def test_gcloud_secret_is_captured_not_printed(self):
        value = "postgresql://demo:placeholder@example.invalid/app?sslmode=require"
        with patch.dict(os.environ, {"DATABASE_URL": ""}):
            with patch.object(migration.shutil, "which", return_value="/usr/bin/gcloud"):
                with patch.object(migration.subprocess, "run") as run:
                    run.return_value.returncode = 0
                    run.return_value.stdout = value
                    self.assertEqual(migration.connection_uri(), value)
                    self.assertTrue(run.call_args.kwargs["capture_output"])

    def test_secret_access_failure_is_explicit(self):
        with patch.dict(os.environ, {"DATABASE_URL": ""}):
            with patch.object(migration.shutil, "which", return_value="/usr/bin/gcloud"):
                with patch.object(migration.subprocess, "run") as run:
                    run.return_value.returncode = 1
                    with self.assertRaisesRegex(ValueError, "Cannot read"):
                        migration.connection_uri()


if __name__ == "__main__":
    unittest.main()
