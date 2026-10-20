import io
import inspect
import json
import logging
import os
import sqlite3
import unittest
from unittest.mock import MagicMock, Mock, patch
from urllib.error import URLError

from fastapi import FastAPI

from api.Endpoint.chat_progress import stream_chat
from api.redis_deps import RedisClient, SetKey
from api.user_deps import UserRegistration, UserRepository
from obervability.http import RequestLoggingMiddleware
from obervability.logger import Logger
from sql.SQLClient import SQLClient
from systems.orch.Orchestrator import Orchestrator
from systems.past_routines_analyzer.PastRoutinesAnalyzer import PastRoutinesAnalyzer
from utils.general.GeminiApiCall import GeminiClient
from utils.pipeline.dataclass.models import PipelineResult
from utils.routinemaker.func.load_prompts import load_prompts
from utils.routinemaker.func.repository import RoutineInputError


class LoggerTests(unittest.TestCase):
    def setUp(self):
        self.root = logging.getLogger()
        self.handlers = self.root.handlers
        self.level = self.root.level
        self.root.handlers = []
        self.output = io.StringIO()
        stdout = patch("sys.stdout", self.output)
        stdout.start()
        self.addCleanup(stdout.stop)
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def tearDown(self):
        for handler in self.root.handlers:
            handler.close()
        self.root.handlers = self.handlers
        self.root.setLevel(self.level)

    def test_get_logger_is_cached_and_does_not_configure_logging(self):
        logger = Logger.get_logger("test.shared.logger")
        self.assertIs(logger, Logger.get_logger("test.shared.logger"))
        self.assertIsInstance(logger, logging.Logger)
        self.assertEqual(logger.handlers, [])
        self.assertEqual(self.root.handlers, [])
        self.assertEqual(self.root.level, self.level)

    def test_default_output_and_severity_filtering(self):
        Logger.configure()
        logger = Logger.get_logger("test.shared.logger")
        logger.debug("hidden")
        logger.info("Processed %d items", 3)
        logger.warning("warning")
        logger.error("error")
        logger.critical("critical")
        lines = self.output.getvalue().splitlines()
        self.assertEqual(len(lines), 4)
        self.assertRegex(lines[0], r"^\d{4}-\d{2}-\d{2} .* INFO test.shared.logger: Processed 3 items$")
        self.assertNotIn("hidden", self.output.getvalue())

    def test_configuration_is_repeatable_and_explicit_level_overrides_environment(self):
        with patch.dict(os.environ, {"LOG_LEVEL": " debug "}):
            Logger.configure()
            handler = self.root.handlers[0]
            Logger.configure()
            self.assertEqual(self.root.handlers, [handler])
            Logger.get_logger("test.shared.logger").debug("visible once")
            Logger.configure("ERROR")
        self.assertEqual(self.output.getvalue().count("visible once"), 1)
        self.assertEqual(self.root.level, logging.ERROR)

    def test_existing_host_handler_and_formatter_are_preserved(self):
        handler = logging.StreamHandler(self.output)
        formatter = logging.Formatter("host: %(message)s")
        handler.setFormatter(formatter)
        self.root.addHandler(handler)
        Logger.configure()
        Logger.get_logger("test.shared.logger").info("event")
        self.assertEqual(self.root.handlers, [handler])
        self.assertIs(handler.formatter, formatter)
        self.assertEqual(self.output.getvalue(), "host: event\n")

    def test_invalid_level_fails_without_modifying_configuration(self):
        for level in ("", "TRACE", "invalid"):
            with self.subTest(level=level), patch.dict(os.environ, {"LOG_LEVEL": level}):
                with self.assertRaisesRegex(ValueError, "LOG_LEVEL"):
                    Logger.configure()
                self.assertEqual(self.root.handlers, [])
                self.assertEqual(self.root.level, self.level)

    def test_exception_tracebacks_and_extra_are_supported(self):
        Logger.configure()
        logger = Logger.get_logger("test.shared.logger")
        with self.assertLogs(logger, level="ERROR") as captured:
            try:
                raise RuntimeError("test failure")
            except RuntimeError:
                logger.exception("Operation failed", extra={"operation": "test"})
        self.assertEqual(captured.records[0].operation, "test")
        self.assertIn("Traceback", captured.output[0])
        self.assertIn("RuntimeError: test failure", captured.output[0])


class RequestLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, app, path="/sessions/private-session", method="GET"):
        messages = []

        async def receive():
            return {"type": "http.request", "body": b"private-body", "more_body": False}

        async def send(message):
            messages.append(message)

        await app({
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
            "root_path": "", "query_string": b"token=private-query",
            "headers": [(b"authorization", b"private-header")],
            "client": ("127.0.0.1", 1234), "server": ("testserver", 80),
        }, receive, send)
        return messages

    async def test_request_logs_template_and_duration_without_private_inputs(self):
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)

        @app.get("/sessions/{session_id}")
        def endpoint(session_id: str):
            return {"ok": True}

        with self.assertLogs("obervability.http", level="INFO") as captured:
            messages = await self.request(app)
        self.assertEqual(messages[0]["status"], 200)
        self.assertEqual(json.loads(messages[-1]["body"]), {"ok": True})
        self.assertEqual(len(captured.records), 1)
        message = captured.records[0].getMessage()
        self.assertIn("method=GET route=/sessions/{session_id} status=200", message)
        self.assertRegex(message, r"duration_ms=\d+\.\d{2}")
        self.assertNotIn("private-", message)

    async def test_unmatched_paths_and_validation_errors_are_warnings(self):
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)

        @app.get("/items/{item_id}")
        def endpoint(item_id: int):
            return item_id

        for path, status, route in (
            ("/private-missing", 404, "<unmatched>"),
            ("/items/private-invalid", 422, "/items/{item_id}"),
        ):
            with self.subTest(path=path), self.assertLogs(
                "obervability.http", level="WARNING",
            ) as captured:
                messages = await self.request(app, path)
            self.assertEqual(messages[0]["status"], status)
            self.assertEqual(captured.records[0].levelno, logging.WARNING)
            self.assertIn(f"route={route} status={status}", captured.output[0])
            self.assertNotIn("private-", captured.output[0])

    async def test_unhandled_error_is_logged_and_reraised_unchanged(self):
        failure = RuntimeError("private-exception")

        async def broken(scope, receive, send):
            raise failure

        with self.assertLogs("obervability.http", level="ERROR") as captured:
            with self.assertRaises(RuntimeError) as raised:
                await self.request(RequestLoggingMiddleware(broken))
        self.assertIs(raised.exception, failure)
        self.assertEqual(len(captured.records), 1)
        self.assertIn("status=500", captured.output[0])
        self.assertIn("error_type=RuntimeError", captured.output[0])
        self.assertNotIn("private-exception", captured.output[0])

    async def test_streamed_messages_pass_through_without_buffering(self):
        expected = [
            {"type": "http.response.start", "status": 200, "headers": []},
            {"type": "http.response.body", "body": b"first", "more_body": True},
            {"type": "http.response.body", "body": b"last", "more_body": False},
        ]

        async def stream(scope, receive, send):
            for message in expected:
                await send(message)

        with self.assertLogs("obervability.http", level="INFO") as captured:
            messages = await self.request(RequestLoggingMiddleware(stream))
        self.assertEqual(messages, expected)
        self.assertEqual(len(captured.records), 1)

    async def test_failure_after_stream_starts_preserves_sent_status(self):
        async def stream(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            raise RuntimeError("private-exception")

        with self.assertLogs("obervability.http", level="ERROR") as captured:
            with self.assertRaises(RuntimeError):
                await self.request(RequestLoggingMiddleware(stream))
        self.assertIn("status=200", captured.output[0])
        self.assertIn("error_type=RuntimeError", captured.output[0])

    async def test_non_http_scopes_pass_through_without_logs(self):
        scopes = []

        async def other(scope, receive, send):
            scopes.append(scope)

        with self.assertNoLogs("obervability.http", level="DEBUG"):
            await RequestLoggingMiddleware(other)({"type": "lifespan"}, None, None)
        self.assertEqual(scopes, [{"type": "lifespan"}])


class OperationTracingTests(unittest.TestCase):
    def test_trace_preserves_signature_and_result_and_measures_milliseconds(self):
        logger = Logger.get_logger("test.operation")
        result = object()

        def operation(value: str, *, enabled: bool = True) -> object:
            """Operation documentation."""
            self.assertEqual((value, enabled), ("private-input", False))
            return result

        traced = Logger.trace(logger)(operation)
        self.assertEqual(inspect.signature(traced), inspect.signature(operation))
        self.assertEqual(traced.__name__, operation.__name__)
        self.assertEqual(traced.__doc__, operation.__doc__)
        with self.assertLogs(logger, level="DEBUG") as captured:
            with patch("obervability.logger.perf_counter", side_effect=[1.0, 1.125]):
                self.assertIs(traced("private-input", enabled=False), result)
        self.assertEqual(len(captured.records), 2)
        self.assertIn("Operation started", captured.output[0])
        self.assertIn("duration_ms=125.00", captured.output[1])
        self.assertNotIn("private-input", "\n".join(captured.output))

    def test_trace_reraises_original_error_without_sensitive_messages_or_error_level_logs(self):
        logger = Logger.get_logger("test.operation")
        failure = ValueError("private-error")

        @Logger.trace(logger)
        def operation(value):
            raise failure

        with self.assertLogs(logger, level="DEBUG") as captured:
            with self.assertRaises(ValueError) as raised:
                operation("private-input")
        self.assertIs(raised.exception, failure)
        self.assertEqual(len(captured.records), 2)
        self.assertTrue(all(record.levelno == logging.DEBUG for record in captured.records))
        output = "\n".join(captured.output)
        self.assertIn("Operation failed", output)
        self.assertIn("error_type=ValueError", output)
        self.assertNotIn("Operation completed", output)
        self.assertNotIn("private-", output)
        self.assertTrue(all(record.exc_info is None for record in captured.records))

    def test_disabled_tracing_calls_operation_without_timing_or_logging(self):
        logger = Mock(spec=logging.Logger)
        logger.isEnabledFor.return_value = False

        @Logger.trace(logger)
        def operation(value):
            return value

        with patch("obervability.logger.perf_counter") as timer:
            self.assertEqual(operation("private-input"), "private-input")
        timer.assert_not_called()
        logger.debug.assert_not_called()


class ServiceLoggingTests(unittest.TestCase):
    def test_service_debug_logs_exclude_payloads_and_credentials(self):
        response = {"candidates": [{"content": {"parts": [{"text": "private-response"}]}}]}
        with self.assertLogs(level="DEBUG") as captured:
            with SQLClient(database_path=":memory:") as client:
                client.execute("CREATE TABLE private_table (value TEXT)")
                client.execute("INSERT INTO private_table VALUES (?)", ("private-value",))
            redis = RedisClient()
            redis.set_turn("private-session", 1, "private-query", "private-response", "no_system")
            redis.set_routine_state("private-session", 99, "private-state")
            with patch(
                "utils.general.GeminiApiCall.urlopen",
                return_value=io.BytesIO(json.dumps(response).encode()),
            ):
                result = GeminiClient(api_key="private-key").generate("private-prompt")
        self.assertEqual(result, "private-response")
        messages = "\n".join(
            record.getMessage() for record in captured.records
            if record.name in (
                "sql.SQLClient", "local_redis_client", "utils.general.GeminiApiCall",
            )
        )
        self.assertIn("SQL statement executing provider=sqlite", messages)
        self.assertIn("Conversation turn stored", messages)
        self.assertIn("Routine state stored", messages)
        self.assertIn("Operation completed operation=GeminiClient.generate", messages)
        self.assertNotIn("private-", messages)
        self.assertNotIn("private_table", messages)

    def test_gemini_failure_preserves_exception_without_logging_credentials_or_prompts(self):
        failure = URLError("private-key private-provider-message")
        with self.assertLogs("utils.general.GeminiApiCall", level="DEBUG") as captured:
            with patch("utils.general.GeminiApiCall.urlopen", side_effect=failure):
                with self.assertRaises(URLError) as raised:
                    GeminiClient(api_key="private-key").generate(
                        "private-prompt", system_prompt="private-system-prompt",
                    )
        self.assertIs(raised.exception, failure)
        self.assertEqual(len(captured.records), 2)
        output = "\n".join(captured.output)
        self.assertIn("error_type=URLError", output)
        self.assertNotIn("private-", output)
        self.assertNotIn("Operation completed", output)

    def test_model_listing_logs_timings_without_page_tokens_or_returned_models(self):
        pages = [
            {"models": [{
                "name": "models/private-model", "supportedGenerationMethods": ["generateContent"],
            }], "nextPageToken": "private-page-token"},
            {"models": []},
        ]
        with self.assertLogs("utils.general.GeminiApiCall", level="DEBUG") as captured:
            with patch(
                "utils.general.GeminiApiCall.urlopen",
                side_effect=[io.BytesIO(json.dumps(page).encode()) for page in pages],
            ) as request:
                models = GeminiClient(api_key="private-key").list_models()
        self.assertEqual(models, ["private-model"])
        self.assertEqual(request.call_count, 2)
        self.assertEqual(len(captured.records), 2)
        self.assertIn("Operation completed operation=GeminiClient.list_models", captured.output[-1])
        self.assertNotIn("private-", "\n".join(captured.output))

    def test_supplied_history_analysis_logs_outcomes_without_user_records(self):
        client = Mock(spec=GeminiClient)
        client.generate.side_effect = [
            '{"status": "ready", "message": ""}', "private-analysis",
        ]
        analyzer = PastRoutinesAnalyzer(client)
        with self.assertLogs(level="DEBUG") as captured:
            response = analyzer.handle("private-query", history="private-history")
        self.assertEqual(response, "private-analysis")
        output = "\n".join(captured.output)
        self.assertIn("Supplied history analysis completed", output)
        self.assertIn("Operation completed operation=PastRoutinesAnalyzer.handle", output)
        self.assertNotIn("private-", output)

    def test_sql_failure_logs_rollback_and_close_without_query_or_values(self):
        with self.assertLogs("sql.SQLClient", level="DEBUG") as captured:
            with self.assertRaises(sqlite3.OperationalError):
                with SQLClient(database_path=":memory:") as client:
                    client.execute("INSERT INTO private_missing_table VALUES (?)", ("private-value",))
        output = "\n".join(captured.output)
        self.assertIn("Operation failed operation=SQLClient.execute", output)
        self.assertIn("Operation completed operation=SQLClient.rollback", output)
        self.assertIn("Operation completed operation=SQLClient.close", output)
        self.assertNotIn("private", output)
        self.assertNotIn("Operation completed operation=SQLClient.commit", output)

    def test_routing_retries_log_attempts_without_invalid_model_output(self):
        selector = Mock(side_effect=["private-invalid-selection", "no_system"])
        orchestrator = Orchestrator(selector)
        with self.assertLogs("utils.orch.func.route", level="DEBUG") as captured:
            result = orchestrator.route({"query": "private-query"})
        self.assertEqual(result, "no_system")
        self.assertEqual(selector.call_count, 2)
        self.assertEqual([record.levelno for record in captured.records], [logging.WARNING, logging.INFO])
        output = "\n".join(captured.output)
        self.assertIn("attempt=1 max_attempts=3", output)
        self.assertIn("Subsystem selected subsystem=no_system", output)
        self.assertNotIn("private-", output)

    def test_session_lifecycle_logs_do_not_expose_session_or_turn_contents(self):
        store = RedisClient()
        with self.assertLogs(level="DEBUG") as captured:
            setter = SetKey(store)
            self.assertTrue(setter.set("private-session"))
            self.assertFalse(setter.set("private-session"))
            store.add_turn("private-session", "private-query", "private-response", "no_system")
            self.assertEqual(store.get_last_turn("private-session")["user_query"], "private-query")
            self.assertTrue(store.delete_session("private-session"))
        output = "\n".join(
            record.getMessage() for record in captured.records if record.name.startswith("local_redis")
        )
        self.assertIn("Conversation session initialized created=True", output)
        self.assertIn("Conversation session initialized created=False", output)
        self.assertIn("Conversation session deletion completed existed=True", output)
        self.assertIn("Operation completed operation=RedisClient.get_last_turn", output)
        self.assertNotIn("private-", output)

    def test_profile_creation_logs_success_only_after_commit(self):
        repository = UserRepository()
        registration = UserRegistration(username="private-user")
        for fail_commit in (False, True):
            connection = MagicMock()
            connection.__enter__.return_value.fetch_one.return_value = {
                "id": 1, "username": registration.username, "weight_unit": "kg",
            }
            failure = RuntimeError("private-commit-error")
            if fail_commit:
                connection.__exit__.side_effect = failure
            with self.subTest(fail_commit=fail_commit), patch.object(
                repository, "connect", return_value=connection,
            ), self.assertLogs("api.user_deps", level="DEBUG") as captured:
                if fail_commit:
                    with self.assertRaises(RuntimeError) as raised:
                        repository.create(registration)
                    self.assertIs(raised.exception, failure)
                else:
                    self.assertEqual(repository.create(registration).username, registration.username)
            output = "\n".join(captured.output)
            self.assertEqual("User profile created" in output, not fail_commit)
            self.assertNotIn("private-", output)

    def test_configuration_failure_does_not_log_private_file_path(self):
        with self.assertLogs("utils.routinemaker.func.load_prompts", level="DEBUG") as captured:
            with self.assertRaises(FileNotFoundError):
                load_prompts("/private-missing-prompt-file.yaml")
        output = "\n".join(captured.output)
        self.assertIn("error_type=FileNotFoundError", output)
        self.assertNotIn("private-", output)


class StreamLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_errors_log_safe_metadata_and_keep_terminal_event_contract(self):
        for failure, status, level in (
            (RuntimeError("private-provider-error"), 500, logging.ERROR),
            (RoutineInputError("private-invalid-input"), 422, logging.WARNING),
        ):
            def run():
                raise failure

            with self.subTest(status=status), self.assertLogs(
                "api.Endpoint.chat_progress", level="DEBUG",
            ) as captured:
                response = stream_chat(run)
                events = [json.loads(chunk) async for chunk in response.body_iterator]
            self.assertEqual(events[-1]["type"], "error")
            self.assertEqual(events[-1]["status"], status)
            self.assertEqual(events[-1].get("message"), str(failure) if status == 422 else None)
            self.assertEqual(sum(record.levelno == level for record in captured.records), 1)
            output = "\n".join(captured.output)
            self.assertIn(f"error_type={type(failure).__name__}", output)
            self.assertNotIn("private-", output)
            self.assertTrue(all(record.exc_info is None for record in captured.records))

    async def test_stream_success_logs_lifecycle_without_response_payload(self):
        with self.assertLogs("api.Endpoint.chat_progress", level="DEBUG") as captured:
            response = stream_chat(lambda: PipelineResult(
                subsystem="no_system", response="private-response",
            ))
            events = [json.loads(chunk) async for chunk in response.body_iterator]
        self.assertEqual(events[-1], {
            "type": "result", "data": {"subsystem": "no_system", "response": "private-response"},
        })
        self.assertEqual(
            [record.getMessage() for record in captured.records],
            ["Chat progress stream started", "Chat progress result queued", "Chat progress stream closed"],
        )
