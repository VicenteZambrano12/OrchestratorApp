"""Live smoke test for Gemini-backed workout history analysis."""

import argparse
from pathlib import Path
import sys
from urllib.error import HTTPError

from systems.past_routines_analyzer.PastRoutinesAnalyzer import PastRoutinesAnalyzer
from utils.general.GeminiApiCall import GeminiClient


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test the past routines analyzer with Gemini."
    )
    parser.add_argument(
        "query",
        nargs="?",
        default="Summarize my past workouts and analyze my progress.",
    )
    parser.add_argument("--language", choices=("EN", "ES"), default="EN")
    parser.add_argument(
        "--history-file",
        type=Path,
        metavar="PATH",
        help="UTF-8 text or JSON file containing past workout records.",
    )
    args = parser.parse_args()
    client = None
    try:
        history = (
            args.history_file.read_text(encoding="utf-8")
            if args.history_file is not None else None
        )
        if history is not None and not history.strip():
            raise ValueError("history file must not be empty")
        client = GeminiClient(max_output_tokens=4096)
        analyzer = PastRoutinesAnalyzer(client)
        result = analyzer.handle(args.query, history=history, language=args.language)
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
        print(f"Past routines analyzer test failed: {exc}", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
