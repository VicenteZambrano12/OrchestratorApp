"""Database-grounded explanations with one generation call per exercise."""

from pathlib import Path

from utils.exercise_explainer.func.generate import generate
from utils.exercise_explainer.dataclass.models import ExerciseExplanation
from utils.exercise_explainer.func.catalog import ExerciseCatalog
from utils.exercise_explainer.func.handle import handle
from utils.exercise_explainer.func.load_prompts import load_prompts
from utils.general.GeminiApiCall import GeminiClient


class ExerciseExplainer:
    """Resolve exercise names against the catalog and explain each matched row."""

    def __init__(
        self,
        client: GeminiClient | None = None,
        prompt_path: str | Path | None = None,
        *,
        database_path: str | Path | None = None,
    ) -> None:
        self._prompts = load_prompts(prompt_path)
        self._catalog = ExerciseCatalog(database_path)
        self._client = (
            GeminiClient(max_output_tokens=4096) if client is None else client
        )

    def _generate(self, stage: str, payload: dict[str, object]) -> str:
        return generate(self._client, self._prompts, stage, payload)

    def handle(
        self,
        query: str,
        *,
        language: str = "EN",
        memory: list[dict[str, str]] | None = None,
    ) -> str | list[ExerciseExplanation]:
        """Explain one exercise or a list; ask for names if none were supplied.

        Named exercises use one extraction call plus one call per unique match.
        Missing or ambiguous names use only the extraction call.
        `memory` holds the latest previous turns (oldest first) so
        follow-ups such as "explain again" can refer to earlier exercises.
        Invalid input/output and provider errors propagate.
        """
        return handle(
            self._generate, query, language=language, memory=memory, catalog=self._catalog
        )