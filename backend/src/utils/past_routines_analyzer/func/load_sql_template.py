"""Choose static workout-history SQL by allowlisted route and provider dialect.

Only weekly aggregation has a PostgreSQL-specific file; other routes share
portable templates. Values are bound by the fetch helper, never interpolated
here, and no model-generated SQL is accepted.

Attributes:
    SQL_TEMPLATES_DIR (Path): Source-relative default query directory.
    _ROUTES (tuple[str, ...]): Allowed filename stems for the three history tasks.
"""

from pathlib import Path

from obervability.logger import Logger
from utils.past_routines_analyzer.dataclass.models import PastRoutinesRouteId

logger = Logger.get_logger(__name__)
SQL_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[3] / "config/sql_templates/past_routines_analyzer"
)
_ROUTES = ("past_day_exercise", "compare_last_two_workouts", "weekly_performance")


@Logger.trace(logger)
def load_sql_template(
    route: PastRoutinesRouteId, templates_dir: str | Path | None = None,
    *, database_type: str = "sqlite",
) -> str:
    """Load a nonempty static query for an allowed retrieval route.

    Args:
        route (PastRoutinesRouteId): Supported history retrieval operation.
        templates_dir (str | Path | None): Override or packaged template directory.
        database_type (str): ``sqlite`` or ``postgresql``.

    Returns:
        str: Original parameterized SQL text ready for SQLClient execution.

    Raises:
        ValueError: Route/provider is unsupported or the query is blank.
        OSError: The selected SQL file cannot be read.
    """
    # 1. Allowlist both filename inputs before constructing a template path.
    if route not in _ROUTES:
        raise ValueError(f"unsupported past routines route: {route}")
    directory = SQL_TEMPLATES_DIR if templates_dir is None else Path(templates_dir)
    if database_type not in ("sqlite", "postgresql"):
        raise ValueError(f"unsupported SQL template provider: {database_type}")
    # 2. Use provider-specific weekly date arithmetic; share other route templates.
    suffix = ".postgresql" if database_type == "postgresql" and route == "weekly_performance" else ""
    sql = (directory / f"{route}{suffix}.sql").read_text(encoding="utf-8")
    if not sql.strip():
        raise ValueError(f"SQL template for {route} is empty")
    return sql
