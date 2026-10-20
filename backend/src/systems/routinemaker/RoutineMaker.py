"""Expose Gemini-backed routine creation, requirement collection, and updates.

Stage-specific YAML instructions drive the delegated routine workflow. SQL-backed
catalog/saved-routine context grounds generation, while a session/user-scoped
store retains drafts. Confirmation saves a new version unless persistence is
explicitly deferred to the client; this facade does not construct SQL itself.
"""

from collections.abc import Mapping
from pathlib import Path

from obervability.logger import Logger
from utils.general.GeminiApiCall import GeminiClient
from utils.routinemaker.dataclass.models import RoutineMakerResult, RoutineParameters, RoutinePlan
from utils.routinemaker.func.generate import generate
from utils.routinemaker.func.handle import RoutineStore, handle
from utils.routinemaker.func.load_prompts import load_prompts
from utils.routinemaker.func.repository import RoutineRepository


logger = Logger.get_logger(__name__)


class RoutineMaker:
    """Own reusable routine dependencies while delegating draft and save policy.

    Attributes:
        _prompts (dict[str, str]): Stage-specific YAML system instructions.
        _client (GeminiClient): Injected or default provider client for stage calls.
        _repository (RoutineRepository): SQL-backed catalog and routine access.
        _state_store (RoutineStore | None): Session/user draft store, lazily resolved
            from Redis dependencies on the first handle call when not injected.
    """

    def __init__(
        self,
        client: GeminiClient | None = None,
        prompt_path: str | Path | None = None,
        *,
        database_path: str | Path | None = None,
        state_store: RoutineStore | None = None,
    ) -> None:
        """Load routine instructions and configure repository/client dependencies.

        Args:
            client (GeminiClient | None): Reuse a client or create an 8192-token one.
            prompt_path (str | Path | None): Override routine-stage YAML path.
            database_path (str | Path | None): Repository database override.
            state_store (RoutineStore | None): Draft-state dependency; None defers
                store acquisition until handling a request.

        Returns:
            None: Initializes prompts, client, repository, and optional draft store.

        Raises:
            ValueError: Prompt contents or default Gemini configuration are invalid.
            OSError: Prompt configuration cannot be read.
            yaml.YAMLError: Prompt configuration cannot be parsed.
        """
        # 1. Resolve stable generation dependencies while leaving draft storage lazy.
        self._prompts = load_prompts(prompt_path)
        self._client = (
            GeminiClient(max_output_tokens=8192) if client is None else client
        )
        self._repository = RoutineRepository(database_path)
        self._state_store = state_store

    def _generate(self, stage: str, payload: dict[str, object]) -> str:
        """Invoke a routine stage using YAML policy and serialized workflow state.

        Args:
            stage (str): Configured workflow stage such as routing or parameters.
            payload (dict[str, object]): Query, routine state, and grounded catalog
                or saved-routine context assembled by the delegated workflow.

        Returns:
            str: Trimmed plain text for parameters, JSON-mode text for other stages.

        Raises:
            KeyError: No prompt is configured for the stage.
            TypeError: Payload values cannot be JSON serialized.
            ValueError: The response is non-text or parameter text is blank.
            Exception: Provider/network failures propagate.
        """
        # 1. Preserve the helper's per-stage MIME policy and system-prompt injection.
        return generate(self._client, self._prompts, stage, payload)

    @Logger.trace(logger)
    def handle(
        self,
        query: str,
        *,
        session_id: str,
        user_id: int,
        parameters: RoutineParameters | Mapping[str, object] | None = None,
        routine: RoutinePlan | None = None,
        language: str = "EN",
        client_saves_routine: bool = False,
    ) -> RoutineMakerResult:
        """Generate database-grounded drafts or process explicit save confirmation.

        Args:
            query (str): Nonblank routine request or follow-up.
            session_id (str): Session scope for draft state.
            user_id (int): Account scope validated by the repository.
            parameters (RoutineParameters | Mapping[str, object] | None): Explicit
                overrides for cached routine requirements.
            routine (RoutinePlan | None): Optional replacement for the cached draft.
            language (str): ``EN`` or ``ES``.
            client_saves_routine (bool): Return a save request on confirmation
                instead of performing server-side routine persistence.

        Returns:
            RoutineMakerResult: Requirement/clarification message, draft preview,
            saved-version result, deferred save request, or no-match result.

        Raises:
            RoutineInputError: Request, identity, or repository inputs are invalid.
            pydantic.ValidationError: Supplied/cached/generated state is invalid
                after any workflow-owned retries.
            Exception: Store, SQL, configuration, and provider failures propagate.
        """
        # 1. Resolve shared draft storage only on first use, preserving injection.
        if self._state_store is None:
            from api.redis_deps import get_routine_store

            self._state_store = get_routine_store()
        # 2. Delegate routing, context assembly, validation, and confirmation together.
        result = handle(
            self._generate,
            query,
            repository=self._repository,
            state_store=self._state_store,
            session_id=session_id,
            user_id=user_id,
            parameters=parameters,
            routine=routine,
            language=language,
            client_saves_routine=client_saves_routine,
        )
        logger.info("Routine request completed status=%s", result.status)
        return result