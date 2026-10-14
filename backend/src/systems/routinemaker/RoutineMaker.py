"""Gemini-backed routine creation, parameter collection, and updates."""

from collections.abc import Mapping
from pathlib import Path

from utils.general.GeminiApiCall import GeminiClient
from utils.routinemaker.dataclass.models import RoutineMakerResult, RoutineParameters, RoutinePlan
from utils.routinemaker.func.generate import generate
from utils.routinemaker.func.handle import RoutineStore, handle
from utils.routinemaker.func.load_prompts import load_prompts
from utils.routinemaker.func.repository import RoutineRepository


class RoutineMaker:
    """Handle a routine turn with session/user-scoped draft state."""

    def __init__(
        self,
        client: GeminiClient | None = None,
        prompt_path: str | Path | None = None,
        *,
        database_path: str | Path | None = None,
        state_store: RoutineStore | None = None,
    ) -> None:
        self._prompts = load_prompts(prompt_path)
        self._client = (
            GeminiClient(max_output_tokens=8192) if client is None else client
        )
        self._repository = RoutineRepository(database_path)
        self._state_store = state_store

    def _generate(self, stage: str, payload: dict[str, object]) -> str:
        return generate(self._client, self._prompts, stage, payload)

    def handle(
        self,
        query: str,
        *,
        session_id: str,
        user_id: int,
        parameters: RoutineParameters | Mapping[str, object] | None = None,
        routine: RoutinePlan | None = None,
        language: str = "EN",
    ) -> RoutineMakerResult:
        """Generate database-backed drafts; save a new version only on confirmation."""
        if self._state_store is None:
            from api.redis_deps import get_routine_store

            self._state_store = get_routine_store()
        return handle(
            self._generate,
            query,
            repository=self._repository,
            state_store=self._state_store,
            session_id=session_id,
            user_id=user_id,
            parameters=parameters,
            routine=routine,
            language=language,
        )