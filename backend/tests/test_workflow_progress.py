import json
import sqlite3
import unittest
from contextlib import closing

from sql.SQLClient import SQLClient
from sql.progress import ProgressConnection
from utils.pipeline.progress import progress_listener, report_progress


class WorkflowProgressTests(unittest.TestCase):
    def test_sql_client_reports_all_query_methods_without_values(self):
        events = []
        with progress_listener(events.append):
            report_progress("history_search", "Searching your logged workout data")
            with SQLClient(database_path=":memory:") as client:
                client.execute("CREATE TABLE items (name TEXT)")
                client.execute("INSERT INTO items VALUES (?)", ("private-value",))
                client.executemany("INSERT INTO items VALUES (?)", [("secret",)])
                self.assertEqual(client.fetch_one("SELECT COUNT(*) AS n FROM items"), {"n": 2})
                self.assertEqual(len(client.fetch_all("SELECT * FROM items")), 2)
        queries = events[1:]
        self.assertEqual(len(queries), 5)
        self.assertEqual(len({event["id"] for event in queries}), 5)
        self.assertTrue(all(event["parent"] == "history_search" for event in queries))
        self.assertTrue(all(event["source"] == "SQLite / :memory:" for event in queries))
        self.assertNotIn("private-value", json.dumps(events))
        self.assertNotIn("secret", json.dumps(events))

    def test_direct_connection_preserves_behavior_and_reports_before_failure(self):
        events = []
        with closing(sqlite3.connect(":memory:", factory=ProgressConnection)) as db:
            db.progress_source = "/private/location/catalog.db"
            with progress_listener(events.append):
                report_progress("exercise_catalog", "Searching the exercise catalog")
                db.execute("CREATE TABLE items (id INTEGER)")
                db.executemany("INSERT INTO items VALUES (?)", [(1,), (2,)])
                self.assertEqual(db.execute("SELECT COUNT(*) FROM items").fetchone(), (2,))
                with self.assertRaises(sqlite3.OperationalError):
                    db.execute("SELECT * FROM missing_table")
        self.assertEqual(events[-1]["sql"], "SELECT * FROM missing_table")
        self.assertTrue(all(event["source"] == "SQLite / catalog.db" for event in events[1:]))
        self.assertNotIn("/private/location", json.dumps(events))

    def test_nested_listeners_restore_parent_and_do_not_leak_between_requests(self):
        outer, inner, next_request = [], [], []
        with closing(sqlite3.connect(":memory:", factory=ProgressConnection)) as db:
            with progress_listener(outer.append):
                report_progress("outer", "Outer")
                with progress_listener(inner.append):
                    db.execute("SELECT 1")
                db.execute("SELECT 2")
            db.execute("SELECT 3")
            with progress_listener(next_request.append):
                db.execute("SELECT 4")
        self.assertEqual(inner[0]["parent"], "request")
        self.assertEqual(outer[-1]["parent"], "outer")
        self.assertEqual(next_request[0]["parent"], "request")
        self.assertEqual(len(outer), 2)
