from pathlib import Path

from utils.past_routines_analyzer.dataclass.models import PastRoutinesRouteId

SQL_TEMPLATES_DIR = (
    Path(__file__).resolve().parents[3] / "config/sql_templates/past_routines_analyzer"
)
_ROUTES = ("past_day_exercise", "compare_last_two_workouts", "weekly_performance")


def load_sql_template(
    route: PastRoutinesRouteId, templates_dir: str | Path | None = None
) -> str:
    """Return the parameterized SQLite query for a past routines route."""
    if route not in _ROUTES:
        raise ValueError(f"unsupported past routines route: {route}")
    directory = SQL_TEMPLATES_DIR if templates_dir is None else Path(templates_dir)
    sql = (directory / f"{route}.sql").read_text(encoding="utf-8")
    if not sql.strip():
        raise ValueError(f"SQL template for {route} is empty")
    return sql
