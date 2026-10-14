"""Two-call Gemini workflow for explaining named exercises."""

from pathlib import Path

from utils.exercise_explainer.generate import generate
from utils.exercise_explainer.handle import handle
from utils.exercise_explainer.load_prompts import load_prompts
from utils.general.GeminiApiCall import GeminiClient


class ExerciseExplainer:
    """Extract exercise names, then return their explanation as plain text."""

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

    def handle(self, query: str, *, language: str = "EN") -> str:
        """Explain one exercise or a list; ask for names if none were supplied.

        Named exercises use exactly two API calls. Missing names use only the
        first call. Invalid input/output and provider errors propagate.
        """
        return handle(self._generate, query, language=language)