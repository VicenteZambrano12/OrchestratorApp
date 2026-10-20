"""Validate top-level routing context and constrain model output before dispatch.

Requests may carry their own subsystem descriptions or use the configured JSON
file. Valid memory is forwarded only when present. Up to three selections are
checked against exact allowed IDs; provider failures are not treated as bad IDs.
"""

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from obervability.logger import Logger
from utils.orch.dataclass.models import MemoryTurn, _RoutingSelection


logger = Logger.get_logger(__name__)


def route(
	selector: Callable[[str, list[dict[str, Any]], str], str],
	systems_path: Path,
	payload: str | Mapping[str, Any],
	language: str | None = None,
) -> str:
	"""Select a configured target or ``no_system`` without invoking that target.

    Args:
        selector (Callable): Model adapter taking query, target list, language,
            and a fourth memory argument only when memory is nonempty.
        systems_path (Path): JSON configuration used when subsystems are omitted.
        payload (str | Mapping[str, Any]): JSON object or mapping with ``query``,
            optional ``language``, ``memory``, and ``subsystems``.
        language (str | None): Explicit language override; otherwise payload or EN.

    Returns:
        str: An exact configured ID or the reserved ``no_system`` fallback ID.

    Raises:
        ValueError: Request/configuration is invalid or three selections fail.
        ValidationError: A prior turn violates the memory schema.
        OSError: The configured systems file cannot be read.
        Exception: Selector/provider failures propagate immediately.
    """
	# 1. Normalize input and language before spending a routing invocation.
	if isinstance(payload, str):
		payload = json.loads(payload)
	if not isinstance(payload, Mapping):
		raise ValueError("payload must be a JSON object")

	query = payload.get("query")
	if not isinstance(query, str) or not query.strip():
		raise ValueError("query must be a non-empty string")
	if language is None:
		language = payload.get("language", "EN")
	if not isinstance(language, str) or language not in ("ES", "EN"):
		raise ValueError("language must be ES (Spanish) or EN (English)")

	# 2. Validate remembered turns before exposing them as model context.
	memory = [
		MemoryTurn.model_validate(turn).model_dump(exclude_unset=True)
		for turn in payload.get("memory") or []
	]

	# 3. Use inline targets when provided; otherwise load the deployment's catalog.
	if "subsystems" in payload:
		subsystems = payload["subsystems"]
	else:
		configuration = json.loads(systems_path.read_text(encoding="utf-8"))
		if not isinstance(configuration, Mapping):
			raise ValueError("systems configuration must be a JSON object")
		subsystems = configuration.get("subsystems")
	if not isinstance(subsystems, list) or not subsystems:
		raise ValueError("subsystems must be a non-empty list")

	# 4. Require unambiguous target identities before constructing the allowlist.
	targets: dict[str, dict[str, Any]] = {}
	for subsystem in subsystems:
		if not isinstance(subsystem, Mapping):
			raise ValueError("each subsystem must be a JSON object")
		subsystem_id = subsystem.get("id")
		description = subsystem.get("description")
		if not isinstance(subsystem_id, str) or not subsystem_id.strip():
			raise ValueError("each subsystem must have a non-empty string id")
		if not isinstance(description, str) or not description.strip():
			raise ValueError(
				"each subsystem must have a non-empty string description"
			)
		if subsystem_id in targets:
			raise ValueError(f"duplicate subsystem id: {subsystem_id}")
		targets[subsystem_id] = dict(subsystem)

	# 5. Retry malformed selections only; never invent a target after exhaustion.
	allowed_ids = set(targets) | {"no_system"}
	last_error: ValidationError | None = None
	for attempt in range(3):
		arguments = (query, [dict(target) for target in targets.values()], language)
		selected_id = selector(*arguments, memory) if memory else selector(*arguments)
		try:
			selection = _RoutingSelection.model_validate(
				{"selected_id": selected_id}, context={"allowed_ids": allowed_ids}
			)
		except ValidationError as error:
			last_error = error
			logger.warning("Subsystem selection rejected attempt=%d max_attempts=3", attempt + 1)
		else:
			logger.info("Subsystem selected subsystem=%s", selection.selected_id)
			return selection.selected_id
	raise ValueError(
		"selector failed to return exactly one allowed routing id "
		f"after 3 attempts; allowed ids: {', '.join(sorted(allowed_ids))}"
	) from last_error
