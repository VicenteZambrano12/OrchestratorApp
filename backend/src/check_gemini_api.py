"""Make one harmless Gemini request and report the response or provider error."""

import argparse
import sys
from time import perf_counter
from urllib.error import HTTPError, URLError

from utils.general.GeminiApiCall import GeminiClient


PROMPT = "Reply with exactly: Gemini connectivity OK"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        help="Override LLM_MODEL for this call; otherwise use the configured model.",
    )
    args = parser.parse_args(argv)
    api_key = ""
    started = perf_counter()

    try:
        client = GeminiClient(model=args.model) if args.model is not None else GeminiClient()
        api_key = client.api_key
        print(f"Model: {client.model}", flush=True)
        print(f"Prompt: {PROMPT}", flush=True)
        response = client.generate(PROMPT)
    except HTTPError as error:
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
        message = str(error).replace(api_key, "[REDACTED]") if api_key else str(error)
        print(f"Gemini network request failed: {message}", file=sys.stderr)
        return 1
    except (ValueError, RuntimeError) as error:
        message = str(error).replace(api_key, "[REDACTED]") if api_key else str(error)
        print(f"Gemini diagnostic failed: {message}", file=sys.stderr)
        return 1

    print(f"Gemini response ({perf_counter() - started:.2f}s):\n{response}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
