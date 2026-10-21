"""Execute allowlisted workout-history templates with bound user/filter values.

The router selects a template, never arbitrary SQL. SQLClient chooses the
provider dialect and manages the connection; user IDs and optional day types
remain parameters rather than interpolated query text.
"""

from collections.abc import Callable

from sql.SQLClient import SQLClient, SQLRow
from utils.past_routines_analyzer.dataclass.models import PastRoutinesRoute
from utils.past_routines_analyzer.func.load_sql_template import load_sql_template


def fetch_history(
    sql_client_factory: Callable[[], SQLClient],
    decision: PastRoutinesRoute,
    user_id: int,
) -> list[SQLRow]:
    """Run the selected provider-compatible template within a managed connection.

    Args:
        sql_client_factory (Callable[[], SQLClient]): Fresh connection factory.
        decision (PastRoutinesRoute): Validated route and optional day filter.
        user_id (int): Positive account identifier; booleans are rejected.

    Returns:
        list[SQLRow]: Database records in template order, possibly empty.

    Raises:
        ValueError: User ID, route/provider, or template contents are invalid.
        OSError: A template file cannot be read.
        Exception: SQL configuration, connection, or execution failures propagate.
    """
    # 1. Scope every query to a valid user before opening any SQL connection.
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    # 2. Weekly queries omit day_type because their aggregate spans all day types.
    parameters: dict[str, int | str | None] = {"user_id": user_id}
    if decision.route != "weekly_performance":
        parameters["day_type"] = decision.day_type
    # 3. Choose dialect from the live client and bind values through its API.
    with sql_client_factory() as client:
        return client.fetch_all(
            load_sql_template(decision.route, database_type=client.database_type), parameters,
        )
