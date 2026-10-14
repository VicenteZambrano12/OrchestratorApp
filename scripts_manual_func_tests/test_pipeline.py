"""Live smoke test for Gemini-backed routing and system execution."""

import argparse
from collections.abc import Mapping
from pathlib import Path
import sys
from time import perf_counter
from typing import Any
from urllib.error import HTTPError

from systems.exercise_explainer.ExerciseExplainer import ExerciseExplainer
from systems.orch.Orchestrator import Orchestrator
from systems.past_routines_analyzer.PastRoutinesAnalyzer import PastRoutinesAnalyzer
from systems.pipeline.Pipeline import Pipeline
from systems.routinemaker.RoutineMaker import RoutineMaker
from utils.general.GeminiApiCall import GeminiClient
from utils.routinemaker.models import RoutineMakerResult, RoutineParameters


class TracingGeminiClient(GeminiClient):
    call_count = 0

    def trace(self, text: str) -> None:
        print(text.replace(self.api_key, "[REDACTED]"), flush=True)

    def generate(self, prompt: str, *, system_prompt: str | None = None) -> str:
        self.call_count += 1
        call_number = self.call_count
        self.trace(f"\n=== API call {call_number}: Gemini generateContent ===")
        self.trace(
            f"Model: {self.model}\nMax output tokens: {self.max_output_tokens}"
            f"\nTimeout: {self.timeout}s"
        )
        self.trace(f"System prompt:\n{system_prompt}")
        self.trace(f"User payload:\n{prompt}")
        started = perf_counter()
        try:
            response = super().generate(prompt, system_prompt=system_prompt)
            self.trace(f"API call {call_number} response:\n{response}")
            return response
        finally:
            self.trace(
                f"API call {call_number} duration: {perf_counter() - started:.3f}s"
            )


class TracingOrchestrator(Orchestrator):
    def route(
        self, payload: str | Mapping[str, Any], language: str | None = None
    ) -> str:
        print("\n=== Orchestrator: selecting a system ===", flush=True)
        target = super().route(payload, language)
        print(f"Selected system: {target}", flush=True)
        if target == "no_system":
            print("No matching system; returning the localized message.", flush=True)
        else:
            print(f"Passing query and language to {target}.", flush=True)
        return target


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test pipeline routing and system execution with Gemini."
    )
    parser.add_argument(
        "query", nargs="?", default="Explain how to perform a squat."
    )
    parser.add_argument("--language", choices=("EN", "ES"), default="EN")
    parser.add_argument(
        "--parameters", default="{}", metavar="JSON",
        help="Previously collected routine parameters as a JSON object.",
    )
    parser.add_argument(
        "--routine-file", type=Path, metavar="PATH",
        help="UTF-8 text file containing an existing routine to update.",
    )
    parser.add_argument(
        "--history-file", type=Path, metavar="PATH",
        help="UTF-8 text or JSON file containing past workout records.",
    )
    args = parser.parse_args()
    client = None
    try:
        parameters = RoutineParameters.model_validate_json(args.parameters)
        routine = (
            args.routine_file.read_text(encoding="utf-8")
            if args.routine_file is not None else None
        )
        history = (
            args.history_file.read_text(encoding="utf-8")
            if args.history_file is not None else None
        )
        if history is not None and not history.strip():
            raise ValueError("history file must not be empty")
        client = TracingGeminiClient(max_output_tokens=4096)
        client.trace(
            f"=== Pipeline input ===\nQuery: {args.query}\nLanguage: {args.language}"
        )
        pipeline = Pipeline(
            TracingOrchestrator.from_gemini(client),
            routine_maker=RoutineMaker(client),
            exercise_explainer=ExerciseExplainer(client),
            past_routines_analyzer=PastRoutinesAnalyzer(client),
        )
        result = pipeline.handle(
            args.query,
            args.language,
            parameters=parameters,
            routine=routine,
            history=history,
        )
        client.trace(f"\n=== Pipeline completed: {client.call_count} API calls ===")
    except HTTPError as exc:
        with exc:
            details = exc.read(65536).decode("utf-8", errors="replace").strip()
        if client is not None:
            details = details.replace(client.api_key, "[REDACTED]")
            print(f"Pipeline stopped after {client.call_count} API calls.", file=sys.stderr)
        print(f"Gemini API error: HTTP {exc.code} {exc.reason}.", file=sys.stderr)
        if details:
            print(details, file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError) as exc:
        details = str(exc)
        if client is not None:
            details = details.replace(client.api_key, "[REDACTED]")
            print(f"Pipeline stopped after {client.call_count} API calls.", file=sys.stderr)
        print(f"Pipeline test failed: {details}", file=sys.stderr)
        return 1
    print("\n=== Final result ===")
    if isinstance(result, RoutineMakerResult):
        client.trace(result.status)
        client.trace(f"Parameters: {result.parameters.model_dump_json()}")
        client.trace(result.message)
    else:
        client.trace(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
