from collections.abc import Callable

from sql.SQLClient import SQLClient, SQLRow
from utils.past_routines_analyzer.dataclass.models import PastRoutinesRoute
from utils.past_routines_analyzer.func.load_sql_template import load_sql_template


def fetch_history(
    sql_client_factory: Callable[[], SQLClient],
    decision: PastRoutinesRoute,
    user_id: int,
) -> list[SQLRow]:
    """Run the route's SQL template for one user and return its rows."""
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    parameters: dict[str, int | str | None] = {"user_id": user_id}
    if decision.route != "weekly_performance":
        parameters["day_type"] = decision.day_type
    with sql_client_factory() as client:
        return client.fetch_all(load_sql_template(decision.route), parameters)
