from pydantic import BaseModel, StrictStr, ValidationInfo, field_validator


class MemoryTurn(BaseModel):
	"""One previous conversation turn passed to the orchestrator as memory."""

	user_query: StrictStr
	system_response: StrictStr
	subsystem_chosen: StrictStr


class _RoutingSelection(BaseModel):
	selected_id: StrictStr

	@field_validator("selected_id")
	@classmethod
	def validate_selected_id(cls, value: str, info: ValidationInfo) -> str:
		if info.context is None or value not in info.context["allowed_ids"]:
			raise ValueError("selection must be exactly one allowed routing id")
		return value
