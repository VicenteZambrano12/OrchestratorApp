"""Expose a two-stage Gemini workflow for caller-supplied workout-history text.

This analyzer does not retrieve SQL history: the caller supplies records. YAML
system prompts drive readiness first and analysis second, with clarification or
no-match responses avoiding the analysis call when records are missing/irrelevant.
"""

from pathlib import Path

from obervability.logger import Logger
from utils.general.GeminiApiCall import GeminiClient
from utils.past_routines_analyzer.func.generate import generate
from utils.past_routines_analyzer.func.handle import handle
from utils.past_routines_analyzer.func.load_prompts import load_prompts


logger = Logger.get_logger(__name__)


class PastRoutinesAnalyzer:
    """Own reusable generation dependencies for supplied-history requests.

    Attributes:
        _prompts (dict[str, str]): Validated parameters/analysis system instructions.
        _client (GeminiClient): Reused injected or default provider client.

    History is per-call context and is never stored on the analyzer instance.
    """

    def __init__(
        self,
        client: GeminiClient | None = None,
        prompt_path: str | Path | None = None,
    ) -> None:
        """Load both stage prompts and initialize the reusable provider client.

        Args:
            client (GeminiClient | None): Existing client or a 4096-token default.
            prompt_path (str | Path | None): Override for supplied-history YAML.

        Returns:
            None: Initializes reusable stage prompts and provider client.

        Raises:
            ValueError: Prompts or default Gemini configuration are invalid.
            OSError: Prompt configuration cannot be read.
            yaml.YAMLError: Prompt configuration cannot be parsed.
        """
        # 1. Fail early on missing instructions before accepting history requests.
        self._prompts = load_prompts(prompt_path)
        self._client = (
            GeminiClient(max_output_tokens=4096) if client is None else client
        )

    def _generate(self, stage: str, payload: dict[str, object]) -> str:
        """Invoke a readiness or analysis stage with separate system instructions.

        Args:
            stage (str): ``parameters`` JSON readiness or ``analysis`` text.
            payload (dict[str, object]): Query, language, and caller-supplied history.

        Returns:
            str: Trimmed stage response.

        Raises:
            KeyError: No system prompt is configured for the stage.
            TypeError: Payload values cannot be JSON serialized.
            ValueError: The provider returns blank/non-text output.
            Exception: Provider/network failures propagate.
        """
        # 1. Keep serialization and output-mode policy in the shared stage adapter.
        return generate(self._client, self._prompts, stage, payload)

    @Logger.trace(logger)
    def handle(
        self,
        query: str,
        *,
        history: str | None = None,
        language: str = "EN",
    ) -> str:
        """Return analysis or a validated readiness fallback.

        Usable history requests use two API calls; other requests use one.

        Args:
            query (str): Nonblank history-analysis request.
            history (str | None): Plain text records, including serialized JSON;
                never interpreted as a file path.
            language (str): ``EN`` or ``ES``.

        Returns:
            str: Analysis, history request, or unrelated-request message.

        Raises:
            ValueError: Input or readiness/message consistency is invalid.
            pydantic.ValidationError: The readiness JSON violates its schema.
            Exception: Provider failures propagate rather than fabricating analysis.
        """
        # 1. Let the helper gate the costly analysis on validated readiness and records.
        return handle(
            self._generate,
            query,
            history=history,
            language=language,
        )
