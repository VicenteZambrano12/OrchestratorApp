"""Live smoke test for Gemini-backed subsystem routing."""

import argparse
import sys
from urllib.error import HTTPError

from systems.orch.Orchestrator import Orchestrator
from utils.general.GeminiApiCall import GeminiClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Test the orchestrator with Gemini.")
    parser.add_argument(
        "query", nargs="?", default="Make me a three-day gym routine."
    )
    parser.add_argument("--language", choices=("EN", "ES"), default="EN")
    args = parser.parse_args()
    client = None
    try:
        client = GeminiClient()
        orchestrator = Orchestrator.from_gemini(client)
        target = orchestrator.route({"query": args.query}, language=args.language)
        message = (
            orchestrator.no_system_message(args.language) if target == "no_system" else None
        )
    except HTTPError as exc:
        with exc:
            details = exc.read(65536).decode("utf-8", errors="replace").strip()
        if client is not None:
            details = details.replace(client.api_key, "[REDACTED]")
        print(f"Gemini API error: HTTP {exc.code} {exc.reason}.", file=sys.stderr)
        if details:
            print(details, file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Orchestrator test failed: {exc}", file=sys.stderr)
        return 1
    print(target)
    if message is not None:
        print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())