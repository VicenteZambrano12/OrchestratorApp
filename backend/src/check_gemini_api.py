"""Diagnose Gemini connectivity independently of the agent orchestration API.

The command sends one fixed text prompt through the shared Gemini client and
reports latency or provider diagnostics. It supports a model override, consumes
provider quota, and redacts the configured API key from displayed error details.
It does not run agent selection, inject a system prompt, or execute tools.
"""

import argparse
import sys
from time import perf_counter
from urllib.error import HTTPError, URLError

from obervability.logger import Logger
from utils.general.GeminiApiCall import GeminiClient


PROMPT = "Reply with exactly: Gemini connectivity OK"
logger = Logger.get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Run the connectivity probe and print its result.

    Args:
        argv: Command-line arguments, or None to use process arguments.

    Returns:
        int: Zero on a generated response; one for handled provider, network,
            configuration, or response failures.

    Raises:
        SystemExit: Argument parsing requests help or rejects invalid arguments.
        OSError: An unhandled local I/O failure occurs outside the guarded
            provider-error body read.
    """
    # 1. Parse only diagnostic options; credentials remain server configuration.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        help="Override LLM_MODEL for this call; otherwise use the configured model.",
    )
    args = parser.parse_args(argv)
    api_key = ""
    started = perf_counter()

    # 2. Use the production transport with a fixed prompt and no agent workflow.
    try:
        client = GeminiClient(model=args.model) if args.model is not None else GeminiClient()
        api_key = client.api_key
        print(f"Model: {client.model}", flush=True)
        print(f"Prompt: {PROMPT}", flush=True)
        response = client.generate(PROMPT)
    except HTTPError as error:
        # 3. Surface provider status and retry hints while redacting the API key.
        logger.error("Gemini diagnostic failed provider_status=%d", error.code)
        print(f"Gemini returned HTTP {error.code}.", file=sys.stderr)
        if error.headers is not None:
            retry_after = error.headers.get("Retry-After")
            if retry_after:
                print(f"Retry-After: {retry_after}", file=sys.stderr)
        try:
            body = error.read().decode("utf-8", errors="replace")
        except OSError as body_error:
            message = str(body_error).replace(api_key, "[REDACTED]")
            print(f"Could not read provider error body: {message}", file=sys.stderr)
        else:
            print(
                f"Provider error body:\n{body.replace(api_key, '[REDACTED]')}",
                file=sys.stderr,
            )
        finally:
            error.close()
        return 1
    except (URLError, TimeoutError) as error:
        # 4. Distinguish network failures from provider and configuration errors.
        logger.error("Gemini diagnostic failed error_type=%s", type(error).__name__)
        message = str(error).replace(api_key, "[REDACTED]") if api_key else str(error)
        print(f"Gemini network request failed: {message}", file=sys.stderr)
        return 1
    except (ValueError, RuntimeError) as error:
        # 5. Report rejected configuration or unusable model output as failure.
        logger.error("Gemini diagnostic failed error_type=%s", type(error).__name__)
        message = str(error).replace(api_key, "[REDACTED]") if api_key else str(error)
        print(f"Gemini diagnostic failed: {message}", file=sys.stderr)
        return 1

    # 6. Report latency only after the provider has produced usable text.
    logger.info("Gemini diagnostic completed duration_ms=%.2f", (perf_counter() - started) * 1000)
    print(f"Gemini response ({perf_counter() - started:.2f}s):\n{response}")
    return 0


if __name__ == "__main__":
    Logger.configure()
    raise SystemExit(main())
