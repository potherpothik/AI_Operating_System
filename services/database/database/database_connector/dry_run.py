from sqlalchemy.engine import Engine

from database.database_connector import query_builder


class DryRunFailed(Exception):
    pass


def estimate(engine: Engine, sql_template: str, params: dict) -> dict:
    """
    EXPLAIN-based impact estimation for a write (Phase 7 doc: "EXPLAIN-
    based impact estimation is the practical default") — never executes
    the statement itself, only asks the planner what it WOULD do. DDL is
    deliberately not handled here: Postgres can't EXPLAIN DDL anyway, and
    the doc's design has DDL never execute directly regardless (always
    routed through migration_adapter), so there's no dry-run-then-execute
    path for it to gate.
    """
    query_type = query_builder.classify(sql_template)
    if query_type != "write":
        raise DryRunFailed(f"dry-run only applies to write statements (UPDATE/DELETE/INSERT), got {query_type!r}")

    explain_template = f"EXPLAIN (FORMAT JSON) {sql_template}"
    built = query_builder.build(explain_template, params)

    with engine.connect() as conn:
        result = conn.execute(built)
        plan_json = result.scalar()

    plan_root = plan_json[0] if isinstance(plan_json, list) else plan_json
    plan = plan_root.get("Plan", {})
    return {
        "estimated_rows_affected": plan.get("Plan Rows", 0),
        "plan_node_type": plan.get("Node Type", "unknown"),
    }
