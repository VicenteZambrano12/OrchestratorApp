"""Validate conversation context and the top-level router's exact selection.

Memory is structured before entering an LLM payload. Selection validation uses
caller-supplied allowed IDs, keeping model output from inventing dispatch targets.
"""

from pydantic import BaseModel, StrictStr, ValidationInfo, field_validator
from utils.routinemaker.dataclass.models import RoutinePlan


class MemoryTurn(BaseModel):
	"""Represent a previous turn shared by top-level and history routers.

	Attributes:
		user_query (StrictStr): Original user request.
		system_response (StrictStr): Stored user-facing response.
		subsystem_chosen (StrictStr): Subsystem that produced the response.
		routine (RoutinePlan | None): Optional structured routine context.
	"""

	user_query: StrictStr
	system_response: StrictStr
	subsystem_chosen: StrictStr
	routine: RoutinePlan | None = None


class _RoutingSelection(BaseModel):
	"""Constrain a model selection to IDs supplied through validation context.

	Attributes:
		selected_id (StrictStr): One configured subsystem ID or ``no_system``.
	"""

	selected_id: StrictStr

	@field_validator("selected_id")
	@classmethod
	def validate_selected_id(cls, value: str, info: ValidationInfo) -> str:
		"""Reject output outside the router's current dispatch vocabulary.

        Args:
            value (str): Strict string already parsed by Pydantic.
            info (ValidationInfo): Context containing ``allowed_ids``.

        Returns:
            str: The unchanged, allowed routing ID.

        Raises:
            ValueError: Context is absent or the ID is not allowed.
            KeyError: Supplied context omits ``allowed_ids``.
        """
		# 1. Bind selection validity to this request's configuration, not the model.
		if info.context is None or value not in info.context["allowed_ids"]:
			raise ValueError("selection must be exactly one allowed routing id")
		return value
