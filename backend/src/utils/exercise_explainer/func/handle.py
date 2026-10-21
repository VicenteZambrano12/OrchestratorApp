"""Coordinate name extraction, SQL catalog resolution, and exercise explanations.

One extraction call uses query/language and optional conversation memory. Missing
names or uncertain catalog matches return clarification without explanation
calls. Successful results preserve database facts and add only generated prose.
"""

from collections.abc import Callable
from obervability.logger import Logger
from utils.exercise_explainer.dataclass.models import ExerciseExplanation, _ExerciseDecision
from utils.exercise_explainer.func.catalog import ExerciseCatalog
from utils.pipeline.progress import report_progress


logger = Logger.get_logger(__name__)


def handle(
    generate_response: Callable[[str, dict[str, object]], str],
    query: str,
    *,
    language: str = "EN",
    memory: list[dict[str, object]] | None = None,
    catalog: ExerciseCatalog | None = None,
) -> str | list[ExerciseExplanation]:
    """Validate a request, collect names, or explain every unique catalog match.

    Args:
        generate_response (Callable[[str, dict[str, object]], str]): Stage adapter.
        query (str): Nonempty exercise request.
        language (str): ``EN`` or ``ES``.
        memory (list[dict[str, object]] | None): Prior turns for follow-up references.
        catalog (ExerciseCatalog | None): Injected resolver or a default catalog.

    Returns:
        str | list[ExerciseExplanation]: Localized/model clarification, or one
        database-grounded explanation per unique resolved exercise.

    Raises:
        ValueError: Input, decision/message consistency, catalog media, or
            explanation text is invalid.
        pydantic.ValidationError: Extraction output or catalog fields fail schema.
        Exception: Provider or SQL failures propagate rather than guessing facts.
    """
    # 1. Reject unsupported requests before building the extraction context.
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if language not in ("EN", "ES"):
        raise ValueError("language must be EN or ES")
    payload: dict[str, object] = {"query": query, "language": language}
    if memory:
        payload["memory"] = memory
    # 2. Validate the extraction decision before trusting names or clarification.
    decision = _ExerciseDecision.model_validate_json(
        generate_response("parameters", payload)
    )
    if not decision.exercises:
        if not decision.message.strip():
            raise ValueError("missing exercises requires a non-empty message")
        logger.info("Exercise explanation outcome=needs_names")
        return decision.message.strip()
    if decision.message.strip():
        raise ValueError("named exercises requires an empty message")
    # 3. Resolve against SQL; ambiguity stops generation and asks the user to choose.
    report_progress("exercise_catalog", "Searching the exercise catalog")
    exercises, unresolved = (catalog or ExerciseCatalog()).resolve(decision.exercises)
    if unresolved:
        logger.info("Exercise explanation outcome=needs_clarification")
        prefix = (
            "Indica el nombre o la variante exacta de estos ejercicios: "
            if language == "ES"
            else "Please clarify the exact name or variant of these exercises: "
        )
        return prefix + "; ".join(unresolved)
    # 4. Validate catalog facts, then add prose without letting the model replace them.
    results: list[ExerciseExplanation] = []
    for index, exercise in enumerate(exercises):
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
    logger.info("Exercise explanation completed count=%d", len(results))
    return results
