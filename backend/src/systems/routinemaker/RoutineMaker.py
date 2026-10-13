"""Gemini-backed routine creation, parameter collection, and updates."""

from collections.abc import Mapping
from pathlib import Path

from utils.general.GeminiApiCall import GeminiClient
from utils.routinemaker.generate import generate
from utils.routinemaker.handle import handle
from utils.routinemaker.load_prompts import load_prompts
from utils.routinemaker.models import RoutineMakerResult, RoutineParameters


class RoutineMaker:
    """Handle one turn with explicit, caller-owned conversation state."""

    def __init__(
        self,
        client: GeminiClient | None = None,
        prompt_path: str | Path | None = None,
    ) -> None:
        self._prompts = load_prompts(prompt_path)
        self._client = (
            GeminiClient(max_output_tokens=4096) if client is None else client
        )

    def _generate(self, stage: str, payload: dict[str, object]) -> str:
        return generate(self._client, self._prompts, stage, payload)

    def handle(
        self,
        query: str,
        *,
        parameters: RoutineParameters | Mapping[str, object] | None = None,
        routine: str | None = None,
        language: str = "EN",
    ) -> RoutineMakerResult:
        """Route, collect missing requirements, or create/update a routine.

        Pass the previous result's parameters and routine on subsequent turns.
        Each turn uses routing plus at most one of the other three prompts.
        Invalid input/output and provider/configuration errors propagate.
        """
        return handle(
            self._generate,
            query,
            parameters=parameters,
            routine=routine,
            language=language,
        )