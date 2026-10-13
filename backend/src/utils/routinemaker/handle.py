from collections.abc import Callable, Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictStr, model_validator

from utils.routinemaker.models import RoutineMakerResult, RoutineParameters


class _RoutingDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["create", "update", "no_match"]
    parameters: RoutineParameters
    message: StrictStr

    @model_validator(mode="after")
    def validate_no_match_message(self) -> "_RoutingDecision":
        if self.intent == "no_match" and not self.message.strip():
            raise ValueError("no_match requires a non-empty message")
        return self


def handle(
    generate_response: Callable[[str, dict[str, object]], str],
    query: str,
    *,
    parameters: RoutineParameters | Mapping[str, object] | None = None,
    routine: str | None = None,
    language: str = "EN",
) -> RoutineMakerResult:
    """Validate a turn and execute routing plus the relevant workflow stage."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if language not in ("EN", "ES"):
        raise ValueError("language must be EN or ES")
    if routine is not None and (
        not isinstance(routine, str) or not routine.strip()
    ):
        raise ValueError("routine must be a non-empty string when provided")
    known = RoutineParameters.model_validate(
        {} if parameters is None else parameters
    )
    payload: dict[str, object] = {
        "query": query,
        "language": language,
        "parameters": known.model_dump(),
        "routine": routine,
    }
    decision = _RoutingDecision.model_validate_json(
        generate_response("routing", payload)
    )
    if decision.intent == "no_match":
        return RoutineMakerResult(
            "no_match", known, decision.message.strip(), routine
        )
    if decision.intent == "update" and routine is None:
        raise ValueError("an existing routine is required for an update")

    merged = RoutineParameters.model_validate({
        **known.model_dump(),
        **decision.parameters.model_dump(exclude_unset=True),
    })
    payload["parameters"] = merged.model_dump()
    payload["intent"] = decision.intent
    if merged.missing_fields:
        payload["missing_parameters"] = list(merged.missing_fields)
        message = generate_response("parameters", payload)
        return RoutineMakerResult("needs_parameters", merged, message, routine)

    stage = "routine_updater" if decision.intent == "update" else "routine_maker"
    generated = generate_response(stage, payload)
    status: Literal["created", "updated"] = (
        "updated" if decision.intent == "update" else "created"
    )
    return RoutineMakerResult(status, merged, generated, generated)
