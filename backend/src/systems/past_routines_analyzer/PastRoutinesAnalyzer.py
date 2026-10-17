"""Two-call Gemini workflow for analyzing supplied workout history."""

from pathlib import Path

from utils.general.GeminiApiCall import GeminiClient
from utils.past_routines_analyzer.func.generate import generate
from utils.past_routines_analyzer.func.handle import handle
from utils.past_routines_analyzer.func.load_prompts import load_prompts


class PastRoutinesAnalyzer:
    """Check a history request, then analyze caller-supplied records."""

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
        history: str | None = None,
        language: str = "EN",
    ) -> str:
        """Return an analysis, a history request, or an unrelated-request message.

        Usable history requests use two API calls; other requests use one.
        History is plain text (including serialized JSON), not a file path.
        Invalid input/output and provider/configuration errors propagate.
        """
        return handle(
            self._generate,
            query,
            history=history,
            language=language,
        )
