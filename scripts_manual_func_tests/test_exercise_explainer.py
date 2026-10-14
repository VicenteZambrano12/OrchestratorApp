"""Live smoke test for Gemini-backed exercise explanations."""

import argparse
import sys
from urllib.error import HTTPError

from systems.exercise_explainer.ExerciseExplainer import ExerciseExplainer
from utils.general.GeminiApiCall import GeminiClient


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test the exercise explainer with Gemini."
    )
    parser.add_argument(
        "query",
        nargs="?",
        default="Explain how to perform a squat.",
        help="Request containing an exercise name or list of names.",
    )
    parser.add_argument("--language", choices=("EN", "ES"), default="EN")
    args = parser.parse_args()
    client = None
    try:
        client = GeminiClient(max_output_tokens=4096)
        explainer = ExerciseExplainer(client)
        result = explainer.handle(args.query, language=args.language)
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
        print(f"Exercise explainer test failed: {exc}", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
