"""Two-call Gemini workflow for analyzing supplied workout history."""

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictStr
import yaml

from utils.general.GeminiApiCall import GeminiClient


class _HistoryDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["ready", "needs_history", "no_match"]
    message: StrictStr


class PastRoutinesAnalyzer:
    """Check a history request, then analyze caller-supplied records."""

    def __init__(
        self,
        client: GeminiClient | None = None,
        prompt_path: str | Path | None = None,
    ) -> None:
        path = (
            Path(prompt_path)
            if prompt_path is not None
            else Path(__file__).resolve().parents[2]
            / "config/prompts/past_routines_analyzer/past_routines_analyzer.yaml"
        )
        prompts = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(prompts, Mapping):
            raise ValueError("history prompts must be a YAML mapping")
        self._prompts: dict[str, str] = {}
        for stage in ("parameters", "analysis"):
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
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        if language not in ("EN", "ES"):
            raise ValueError("language must be EN or ES")
        if history is not None and (
            not isinstance(history, str) or not history.strip()
        ):
            raise ValueError("history must be a non-empty string when provided")
        payload: dict[str, object] = {
            "query": query,
            "language": language,
            "history": history,
        }
        decision = _HistoryDecision.model_validate_json(
            self._generate("parameters", payload)
        )
        if decision.status != "ready":
            if not decision.message.strip():
                raise ValueError(f"{decision.status} requires a non-empty message")
            return decision.message.strip()
        if history is None:
            raise ValueError("analysis requires supplied history")
        if decision.message.strip():
            raise ValueError("ready requires an empty message")
        return self._generate("analysis", payload)
