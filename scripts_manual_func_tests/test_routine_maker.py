"""Live smoke test for Gemini-backed routine creation and updates."""

import argparse
from pathlib import Path
import sys
from urllib.error import HTTPError

from systems.routinemaker.RoutineMaker import RoutineMaker, RoutineParameters
from utils.general.GeminiApiCall import GeminiClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Test the routine maker with Gemini.")
    parser.add_argument(
        "query",
        nargs="?",
        default=(
            "Make me a beginner routine for three days per week, "
            "one hour per training session."
        ),
    )
    parser.add_argument("--language", choices=("EN", "ES"), default="EN")
    parser.add_argument(
        "--parameters",
        default="{}",
        metavar="JSON",
        help="Previously collected routine parameters as a JSON object.",
    )
    parser.add_argument(
        "--routine-file",
        type=Path,
        metavar="PATH",
        help="UTF-8 text file containing an existing routine to update.",
    )
    args = parser.parse_args()
    client = None
    try:
        parameters = RoutineParameters.model_validate_json(args.parameters)
        routine = (
            args.routine_file.read_text(encoding="utf-8")
            if args.routine_file is not None else None
        )
        client = GeminiClient(max_output_tokens=4096)
        maker = RoutineMaker(client)
        result = maker.handle(
            args.query,
            parameters=parameters,
            routine=routine,
            language=args.language,
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
        print(f"Routine maker test failed: {exc}", file=sys.stderr)
        return 1
    print(result.status)
    print(f"Parameters: {result.parameters.model_dump_json()}")
    print(result.message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())