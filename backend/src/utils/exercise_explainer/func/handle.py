from collections.abc import Callable
from utils.exercise_explainer.dataclass.models import ExerciseExplanation, _ExerciseDecision
from utils.exercise_explainer.func.catalog import ExerciseCatalog
from utils.pipeline.progress import report_progress


def handle(
    generate_response: Callable[[str, dict[str, object]], str],
    query: str,
    *,
    language: str = "EN",
    memory: list[dict[str, object]] | None = None,
    catalog: ExerciseCatalog | None = None,
) -> str | list[ExerciseExplanation]:
    """Validate a request, collect names, or explain the supplied exercises."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if language not in ("EN", "ES"):
        raise ValueError("language must be EN or ES")
    payload: dict[str, object] = {"query": query, "language": language}
    if memory:
        payload["memory"] = memory
    decision = _ExerciseDecision.model_validate_json(
        generate_response("parameters", payload)
    )
    if not decision.exercises:
        if not decision.message.strip():
            raise ValueError("missing exercises requires a non-empty message")
        return decision.message.strip()
    if decision.message.strip():
        raise ValueError("named exercises requires an empty message")
    report_progress("exercise_catalog", "Searching the exercise catalog")
    exercises, unresolved = (catalog or ExerciseCatalog()).resolve(decision.exercises)
    if unresolved:
        prefix = (
            "Indica el nombre o la variante exacta de estos ejercicios: "
            if language == "ES"
            else "Please clarify the exact name or variant of these exercises: "
        )
        return prefix + "; ".join(unresolved)
    results: list[ExerciseExplanation] = []
    for index, exercise in enumerate(exercises):
        # Validate catalog values before sending context to the provider.
        validated = ExerciseExplanation(**exercise, llm_explanation="pending")
        report_progress(f"exercise_explanation_{index}", "Preparing an exercise explanation")
        explanation = generate_response("explanation", {**payload, "exercise": exercise})
        if not isinstance(explanation, str) or not explanation.strip():
            raise ValueError("Gemini returned an empty or non-text explanation response")
        results.append(
            ExerciseExplanation(
                **validated.model_dump(exclude={"llm_explanation"}),
                llm_explanation=explanation.strip(),
            )
        )
    return results
