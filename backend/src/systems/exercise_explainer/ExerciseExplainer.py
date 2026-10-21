"""Expose database-grounded exercise explanations with contextual name extraction.

YAML supplies separate extraction and explanation system instructions. The
helper uses one extraction call, resolves names through SQL, and makes one text
call per unique match. Missing/ambiguous names ask for clarification rather than
allowing the model to invent catalog metadata.
"""

from pathlib import Path

from obervability.logger import Logger
from utils.exercise_explainer.func.generate import generate
from utils.exercise_explainer.dataclass.models import ExerciseExplanation
from utils.exercise_explainer.func.catalog import ExerciseCatalog
from utils.exercise_explainer.func.handle import handle
from utils.exercise_explainer.func.load_prompts import load_prompts
from utils.general.GeminiApiCall import GeminiClient


logger = Logger.get_logger(__name__)


class ExerciseExplainer:
    """Own reusable prompts, catalog access, and the exercise generation adapter.

    Attributes:
        _prompts (dict[str, str]): Validated parameters/explanation system prompts.
        _catalog (ExerciseCatalog): Resolver retaining the SQL database override.
        _client (GeminiClient): Injected or default client shared across stage calls.

    Conversation memory belongs to each handle call, not to this reusable object.
    """

    def __init__(
        self,
        client: GeminiClient | None = None,
        prompt_path: str | Path | None = None,
        *,
        database_path: str | Path | None = None,
    ) -> None:
        """Load instructions and configure catalog/provider dependencies.

        Args:
            client (GeminiClient | None): Reuse a client, or create a 4096-token one.
            prompt_path (str | Path | None): Override for exercise stage YAML.
            database_path (str | Path | None): SQLClient SQLite override; None uses
                configured provider selection.

        Returns:
            None: Initializes reusable prompts, catalog access, and provider client.

        Raises:
            ValueError: Prompt contents or default Gemini configuration are invalid.
            OSError: Prompt configuration cannot be read.
            yaml.YAMLError: Prompt configuration cannot be parsed.
        """
        # 1. Validate reusable instructions now; SQL connections remain per resolution.
        self._prompts = load_prompts(prompt_path)
        self._catalog = ExerciseCatalog(database_path)
        self._client = (
            GeminiClient(max_output_tokens=4096) if client is None else client
        )

    def _generate(self, stage: str, payload: dict[str, object]) -> str:
        """Invoke a stage with JSON user context and its separate system prompt.

        Args:
            stage (str): ``parameters`` extraction or ``explanation`` generation.
            payload (dict[str, object]): Query, language, optional memory/catalog row.

        Returns:
            str: Trimmed JSON decision or explanation text.

        Raises:
            KeyError: The stage has no prompt.
            ValueError: The provider returns blank/non-text output.
            TypeError: Payload values cannot be JSON serialized.
            Exception: Provider/network failures propagate.
        """
        # 1. Reuse the same client and validated instructions for every stage.
        return generate(self._client, self._prompts, stage, payload)

    @Logger.trace(logger)
    def handle(
        self,
        query: str,
        *,
        language: str = "EN",
        memory: list[dict[str, object]] | None = None,
    ) -> str | list[ExerciseExplanation]:
        """Explain catalog matches or ask for missing/unambiguous exercise names.

        Named exercises use one extraction call plus one call per unique match.
        Missing or ambiguous names use only the extraction call.

        Args:
            query (str): Nonblank exercise question.
            language (str): ``EN`` or ``ES``.
            memory (list[dict[str, object]] | None): Latest prior turns, oldest
                first, so follow-ups such as "explain again" can resolve references.

        Returns:
            str | list[ExerciseExplanation]: Clarification text or catalog records
            with separately generated explanations.

        Raises:
            ValueError: Input, decision consistency, media, or output is invalid.
            pydantic.ValidationError: Model decision or catalog schema is invalid.
            Exception: SQL and provider failures propagate without guessed records.
        """
        # 1. Delegate extraction, authoritative lookup, and per-match validation together.
        return handle(
            self._generate, query, language=language, memory=memory, catalog=self._catalog
        )