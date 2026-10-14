"""Two-call Gemini workflow for explaining named exercises."""

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StrictStr, StringConstraints
import yaml

from utils.general.GeminiApiCall import GeminiClient


class _ExerciseDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    exercises: list[
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    ]
    message: StrictStr


class ExerciseExplainer:
    """Extract exercise names, then return their explanation as plain text."""

    def __init__(
        self,
        client: GeminiClient | None = None,
        prompt_path: str | Path | None = None,
    ) -> None:
        path = (
            Path(prompt_path)
            if prompt_path is not None
            else Path(__file__).resolve().parents[2]
            / "config/prompts/exercise_explainer/exercise_explainer.yaml"
        )
        prompts = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(prompts, Mapping):
            raise ValueError("exercise prompts must be a YAML mapping")
        self._prompts: dict[str, str] = {}
        for stage in ("parameters", "explanation"):
            prompt = prompts.get(stage)
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError(f"{stage} must be a non-empty prompt")
            self._prompts[stage] = prompt
        self._client = (
            GeminiClient(max_output_tokens=4096) if client is None else client
        )

    def _generate(self, stage: str, payload: dict[str, object]) -> str:
        response = self._client.generate(
            json.dumps(payload, ensure_ascii=True),
            system_prompt=self._prompts[stage],
        )
        if not isinstance(response, str) or not response.strip():
            raise ValueError(f"Gemini returned an empty or non-text {stage} response")
        return response.strip()

    def handle(self, query: str, *, language: str = "EN") -> str:
        """Explain one exercise or a list; ask for names if none were supplied.

        Named exercises use exactly two API calls. Missing names use only the
        first call. Invalid input/output and provider errors propagate.
        """
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        if language not in ("EN", "ES"):
            raise ValueError("language must be EN or ES")
        payload: dict[str, object] = {"query": query, "language": language}
        decision = _ExerciseDecision.model_validate_json(
            self._generate("parameters", payload)
        )
        if not decision.exercises:
            if not decision.message.strip():
                raise ValueError("missing exercises requires a non-empty message")
            return decision.message.strip()
        if decision.message.strip():
            raise ValueError("named exercises requires an empty message")
        payload["parameters"] = {"exercises": decision.exercises}
        return self._generate("explanation", payload)