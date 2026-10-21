"""Configure backend logging and trace synchronous infrastructure operations.

Entry points initialize the root logger; modules obtain named standard-library
loggers without installing their own handlers. The tracing decorator records
operation names, timing, and exception types, but excludes arguments and results
so credentials, prompts, and user data are not copied into diagnostic logs.
"""

from collections.abc import Callable
from functools import wraps
import logging
import os
import sys
from time import perf_counter
from typing import ParamSpec, TypeVar


P = ParamSpec("P")
R = TypeVar("R")


class Logger:
    """Provide stateless logging configuration and synchronous tracing helpers.

    This class holds no instance state. Configuration affects the process-wide
    root logger, and named logger instances are managed by ``logging`` itself.
    """

    @staticmethod
    def configure(level: str | None = None) -> None:
        """Set the root log level while preserving host-installed handlers.

        Args:
            level: Explicit level name, or None to read LOG_LEVEL with INFO
                as the default.

        Returns:
            None: Configures process-wide logging in place.

        Raises:
            ValueError: The normalized level name is unsupported.
        """
        # 1. Validate a shared level before mutating process-wide logging state.
        name = (level if level is not None else os.environ.get("LOG_LEVEL", "INFO")).strip().upper()
        levels = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        if name not in levels:
            raise ValueError("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL.")
        # 2. Install stdout formatting only when the host has no handlers.
        logging.basicConfig(
            level=levels[name],
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            stream=sys.stdout,
        )
        logging.getLogger().setLevel(levels[name])

    @staticmethod
    def get_logger(name: str) -> logging.Logger:
        """Retrieve a named logger without installing handlers.

        Args:
            name: Logger namespace, normally the calling module's ``__name__``.

        Returns:
            logging.Logger: Standard-library logger cached under that name.
        """
        # 1. Reuse the logging registry so module loggers share root policy.
        return logging.getLogger(name)

    @staticmethod
    def trace(logger: logging.Logger) -> Callable[[Callable[P, R]], Callable[P, R]]:
        """Build a signature-preserving decorator for synchronous operations.

        Args:
            logger: Logger receiving DEBUG operation and duration records.

        Returns:
            Callable[[Callable[P, R]], Callable[P, R]]: Decorator that preserves
                the wrapped callable's parameter and return types.
        """
        # 1. Capture only the logger; invocation data remains outside log records.
        def decorate(function: Callable[P, R]) -> Callable[P, R]:
            """Wrap a callable with optional operation timing.

            Args:
                function: Synchronous operation to instrument.

            Returns:
                Callable[P, R]: Metadata-preserving wrapper with the same contract.
            """
            # 1. Preserve function metadata for frameworks and diagnostics.
            @wraps(function)
            def traced(*args: P.args, **kwargs: P.kwargs) -> R:
                """Execute the operation and trace its outcome when enabled.

                Args:
                    *args: Positional arguments forwarded unchanged.
                    **kwargs: Keyword arguments forwarded unchanged.

                Returns:
                    R: The wrapped operation's result.

                Raises:
                    Exception: Any wrapped failure is logged by type and
                        re-raised unchanged.
                """
                # 1. Avoid timing and log overhead when DEBUG is disabled.
                if not logger.isEnabledFor(logging.DEBUG):
                    return function(*args, **kwargs)
                # 2. Measure the call without exposing its arguments or result.
                started = perf_counter()
                logger.debug("Operation started operation=%s", function.__qualname__)
                try:
                    result = function(*args, **kwargs)
                except Exception as error:
                    # 3. Preserve failure semantics while recording diagnostic timing.
                    logger.debug(
                        "Operation failed operation=%s duration_ms=%.2f error_type=%s",
                        function.__qualname__, (perf_counter() - started) * 1000,
                        type(error).__name__,
                    )
                    raise
                # 4. Record successful completion and preserve the original result.
                logger.debug(
                    "Operation completed operation=%s duration_ms=%.2f",
                    function.__qualname__, (perf_counter() - started) * 1000,
                )
                return result
            return traced
        return decorate