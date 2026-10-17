import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from utils.orch.dataclass.models import MemoryTurn, _RoutingSelection


def route(
	selector: Callable[[str, list[dict[str, Any]], str], str],
	systems_path: Path,
	payload: str | Mapping[str, Any],
	language: str | None = None,
) -> str:
	"""Validate a routing request and select an ID with up to three attempts."""
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

	memory = [
		MemoryTurn.model_validate(turn).model_dump(exclude_unset=True)
		for turn in payload.get("memory") or []
	]

	if "subsystems" in payload:
		subsystems = payload["subsystems"]
	else:
		configuration = json.loads(systems_path.read_text(encoding="utf-8"))
		if not isinstance(configuration, Mapping):
			raise ValueError("systems configuration must be a JSON object")
		subsystems = configuration.get("subsystems")
	if not isinstance(subsystems, list) or not subsystems:
		raise ValueError("subsystems must be a non-empty list")

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

	allowed_ids = set(targets) | {"no_system"}
	last_error: ValidationError | None = None
	for _ in range(3):
		arguments = (query, [dict(target) for target in targets.values()], language)
		selected_id = selector(*arguments, memory) if memory else selector(*arguments)
		try:
			selection = _RoutingSelection.model_validate(
				{"selected_id": selected_id}, context={"allowed_ids": allowed_ids}
			)
		except ValidationError as error:
			last_error = error
		else:
			return selection.selected_id
	raise ValueError(
		"selector failed to return exactly one allowed routing id "
		f"after 3 attempts; allowed ids: {', '.join(sorted(allowed_ids))}"
	) from last_error
