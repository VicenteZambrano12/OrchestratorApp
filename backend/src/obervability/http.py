"""Observe ASGI HTTP outcomes at the application boundary.

The middleware measures request duration and response status without consuming
request bodies or response streams. It logs route templates instead of raw URLs,
keeping caller-specific path values out of ordinary request records. Non-HTTP
ASGI traffic is forwarded without instrumentation.
"""

import logging
from time import perf_counter

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from obervability.logger import Logger


logger = Logger.get_logger(__name__)


class RequestLoggingMiddleware:
    """Wrap an ASGI application with status-aware request logging.

    Attributes:
        app (ASGIApp): Downstream application, including routers and mounts.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Bind the downstream application without changing its routing.

        Args:
            app: ASGI application to observe.

        Returns:
            None: Stores the downstream application.
        """
        # 1. Retain the application so ASGI messages can be forwarded unchanged.
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Forward an ASGI request and log its terminal HTTP outcome.

        Args:
            scope: ASGI connection metadata, updated by downstream routing.
            receive: Incoming ASGI message callable.
            send: Outgoing ASGI message callable.

        Returns:
            None: Sends responses through the supplied ASGI channel.

        Raises:
            Exception: Downstream failures propagate after their type is recorded.
        """
        # 1. Keep lifespan and other non-HTTP protocols outside HTTP diagnostics.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 2. Default to failure until the application emits a response status.
        started = perf_counter()
        status = 500
        error_type = None

        async def send_response(message: Message) -> None:
            """Capture response status without buffering response content.

            Args:
                message: ASGI response message forwarded to the server.

            Returns:
                None: Sends the original message unchanged.

            Raises:
                Exception: Send-channel failures propagate to the request wrapper.
            """
            # 1. Observe headers only, preserving streaming and body privacy.
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        # 3. Log both normal completion and exceptions without handling the error.
        try:
            await self.app(scope, receive, send_response)
        except Exception as error:
            error_type = type(error).__name__
            raise
        finally:
            route = getattr(scope.get("route"), "path", "<unmatched>")
            level = (
                logging.ERROR if error_type or status >= 500
                else logging.WARNING if status >= 400 else logging.INFO
            )
            logger.log(
                level,
                "HTTP method=%s route=%s status=%d duration_ms=%.2f error_type=%s",
                scope["method"], route, status,
                (perf_counter() - started) * 1000, error_type,
            )
