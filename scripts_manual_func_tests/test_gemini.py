"""Executable smoke test for the reusable Gemini client."""

import argparse
import sys
from urllib.error import HTTPError

from backend.src.utils.general.GeminiApiCall import GeminiClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Test a text-only Gemini API call.")
    parser.add_argument(
        "prompt",
        nargs="?",
        default="hello!",
    )
    parser.add_argument("--model", help="Override LLM_MODEL from the environment or .env.")
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List available generateContent models without generating text.",
    )
    args = parser.parse_args()
    client = None
    try:
        client = GeminiClient() if args.model is None else GeminiClient(model=args.model)
        if args.list_models:
            print("\n".join(client.list_models()))
            return 0
        text = client.generate(args.prompt)
    except HTTPError as exc:
        with exc:
            details = exc.read(65536).decode("utf-8", errors="replace").strip()
        if client is not None:
            details = details.replace(client.api_key, "[REDACTED]")
        print(
            f"Gemini API error: HTTP {exc.code} {exc.reason}.",
            file=sys.stderr,
        )
        if details:
            print(details, file=sys.stderr)
        if exc.code == 404:
            print(
                f"Model {client.model if client is not None else args.model!r} "
                "may be unavailable or not support generateContent. "
                "Run with --list-models, then select an available model with --model MODEL_ID.",
                file=sys.stderr,
            )
        return 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Gemini test failed: {exc}", file=sys.stderr)
        return 1
    print(f"Model: {client.model}\nResponse:\n{text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())