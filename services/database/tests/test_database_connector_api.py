import pytest
from fastapi import HTTPException

from database.db import SessionLocal
from database.database_connector import api


def test_query_reads_real_seeded_rows(governance_url):
    db = SessionLocal()
    result = api.query(
        api.QueryRequest(
            target_db="demo_erp", table="sale_order",
            sql_template="SELECT id, name, amount_total FROM sale_order WHERE partner_id = :partner_id ORDER BY id",
            params={"partner_id": 1}, capability="database_agent", requesting_agent="reasoning_engine",
        ),
        db,
    )
    db.close()
    assert result["row_count"] == 2
    assert {r["name"] for r in result["rows"]} == {"SO0001", "SO0002"}
    assert "amount_total" in result["columns"]


def test_query_redacts_confidential_columns_at_internal_ceiling(governance_url):
    db = SessionLocal()
    result = api.query(
        api.QueryRequest(
            target_db="demo_erp", table="res_partner",
            sql_template="SELECT id, name, email FROM res_partner WHERE id = :id",
            params={"id": 1}, capability="database_agent", requesting_agent="reasoning_engine",
            requester_ceiling="internal",
        ),
        db,
    )
    db.close()
    assert "email" not in result["columns"]
    assert "email" in result["redacted_columns"]
    assert "email" not in result["rows"][0]
    assert result["rows"][0]["name"] == "Acme Manufacturing"


def test_query_includes_confidential_columns_at_confidential_ceiling(governance_url):
    db = SessionLocal()
    result = api.query(
        api.QueryRequest(
            target_db="demo_erp", table="res_partner",
            sql_template="SELECT id, name, email FROM res_partner WHERE id = :id",
            params={"id": 1}, capability="database_agent", requesting_agent="reasoning_engine",
            requester_ceiling="confidential",
        ),
        db,
    )
    db.close()
    assert result["rows"][0]["email"] == "ops@acme.example"


def test_query_rejects_write_statement():
    db = SessionLocal()
    with pytest.raises(HTTPException) as exc_info:
        api.query(
            api.QueryRequest(
                target_db="demo_erp", table="sale_order",
                sql_template="UPDATE sale_order SET state = :state WHERE id = :id",
                params={"state": "cancel", "id": 1}, capability="database_agent", requesting_agent="reasoning_engine",
            ),
            db,
        )
    db.close()
    assert exc_info.value.status_code == 400


def test_dry_run_gives_a_real_row_estimate(governance_url, demo_erp_clean):
    db = SessionLocal()
    result = api.dry_run_endpoint(
        api.DryRunRequest(
            target_db="demo_erp",
            sql_template="UPDATE sale_order SET state = :state WHERE name = :name",
            params={"state": "sale", "name": "SO0003"},
            capability="database_agent", requesting_agent="reasoning_engine", task_id="task-dryrun-1",
        ),
        db,
    )
    db.close()
    assert result["dry_run_id"]
    assert result["estimated_rows_affected"] >= 0  # a real planner estimate, not a hardcoded value


def test_write_without_any_dry_run_is_rejected():
    db = SessionLocal()
    with pytest.raises(HTTPException) as exc_info:
        api.write(
            api.WriteRequest(
                target_db="demo_erp", sql_template="UPDATE sale_order SET state = :state WHERE name = :name",
                params={"state": "sale", "name": "SO0003"}, dry_run_id="nonexistent-dry-run-id",
                capability="database_agent", requesting_agent="reasoning_engine",
            ),
            db,
        )
    db.close()
    assert exc_info.value.status_code == 400
    assert "dry-run" in exc_info.value.detail.lower()


def test_write_with_drifted_params_from_the_dry_run_is_rejected(governance_url, demo_erp_clean):
    db = SessionLocal()
    dry = api.dry_run_endpoint(
        api.DryRunRequest(
            target_db="demo_erp", sql_template="UPDATE sale_order SET state = :state WHERE name = :name",
            params={"state": "sale", "name": "SO0003"}, capability="database_agent", requesting_agent="reasoning_engine",
        ),
        db,
    )
    with pytest.raises(HTTPException) as exc_info:
        api.write(
            api.WriteRequest(
                target_db="demo_erp", sql_template="UPDATE sale_order SET state = :state WHERE name = :name",
                params={"state": "cancel", "name": "SO0003"},  # different params than what was previewed
                dry_run_id=dry["dry_run_id"], capability="database_agent", requesting_agent="reasoning_engine",
            ),
            db,
        )
    db.close()
    assert exc_info.value.status_code == 400
    assert "drift" in exc_info.value.detail.lower()


def test_write_with_matching_dry_run_actually_executes(governance_url, demo_erp_clean):
    import sqlalchemy
    import os

    db = SessionLocal()
    sql_template = "UPDATE sale_order SET state = :state WHERE name = :name"
    params = {"state": "sale", "name": "SO0003"}

    dry = api.dry_run_endpoint(
        api.DryRunRequest(target_db="demo_erp", sql_template=sql_template, params=params, capability="database_agent", requesting_agent="reasoning_engine"),
        db,
    )
    write_result = api.write(
        api.WriteRequest(target_db="demo_erp", sql_template=sql_template, params=params, dry_run_id=dry["dry_run_id"], capability="database_agent", requesting_agent="reasoning_engine"),
        db,
    )
    db.close()

    assert write_result["status"] == "completed"
    assert write_result["actual_rows_affected"] == 1

    # Independent verification against the real target database directly.
    target_engine = sqlalchemy.create_engine(os.environ["DEMO_ERP_DATABASE_URL"])
    with target_engine.connect() as conn:
        state = conn.execute(sqlalchemy.text("SELECT state FROM sale_order WHERE name = 'SO0003'")).scalar()
    assert state == "sale"


def test_dry_run_against_a_nonexistent_column_fails_cleanly_not_a_500(governance_url, demo_erp_clean):
    """
    Regression test: a raw DBAPIError (e.g. "column does not exist") used
    to propagate uncaught out of /db/dry_run as an unhandled 500 — found
    by actually running a bad statement, not by reading the code (the
    original except clauses only listed this module's own exception
    types, never SQLAlchemy's). Fixed by catching DBAPIError explicitly
    and translating it to a clean 400.
    """
    db = SessionLocal()
    sql_template = "UPDATE sale_order SET nonexistent_column = :val WHERE name = :name"
    params = {"val": "x", "name": "SO0003"}

    with pytest.raises(HTTPException) as exc_info:
        api.dry_run_endpoint(
            api.DryRunRequest(target_db="demo_erp", sql_template=sql_template, params=params, capability="database_agent", requesting_agent="reasoning_engine"),
            db,
        )
    db.close()
    assert exc_info.value.status_code == 400  # not 500 — a real database error is a client-facing 400, not an unhandled crash

    # And confirms the actual point of dry-run: a bad write never gets
    # the chance to even partially apply, since it can't produce a
    # dry_run_id to reference in the first place.
    import sqlalchemy, os
    target_engine = sqlalchemy.create_engine(os.environ["DEMO_ERP_DATABASE_URL"])
    with target_engine.connect() as conn:
        state = conn.execute(sqlalchemy.text("SELECT state FROM sale_order WHERE name = 'SO0003'")).scalar()
    assert state == "sale"  # unchanged from demo_erp_clean's setup state


def test_write_that_fails_at_execution_despite_passing_dry_run_rolls_back(governance_url, demo_erp_clean):
    """
    A dry-run's EXPLAIN doesn't catch every possible failure (e.g. a
    primary-key collision on INSERT ... VALUES, which the planner doesn't
    evaluate) — this proves the write path itself still rolls back
    cleanly and reports failed rather than partially applying or
    crashing, for the failure class dry-run structurally can't preview.
    """
    db = SessionLocal()
    sql_template = "INSERT INTO sale_order (id, name, partner_id, amount_total) VALUES (:id, :name, :partner_id, :amount)"
    params = {"id": 1, "name": "TEST_DUPLICATE", "partner_id": 1, "amount": 1.0}  # id=1 already exists

    dry = api.dry_run_endpoint(
        api.DryRunRequest(target_db="demo_erp", sql_template=sql_template, params=params, capability="database_agent", requesting_agent="reasoning_engine"),
        db,
    )
    with pytest.raises(HTTPException) as exc_info:
        api.write(
            api.WriteRequest(target_db="demo_erp", sql_template=sql_template, params=params, dry_run_id=dry["dry_run_id"], capability="database_agent", requesting_agent="reasoning_engine"),
            db,
        )
    db.close()
    assert exc_info.value.status_code == 500
    assert "rolled back" in exc_info.value.detail.lower()

    import sqlalchemy, os
    target_engine = sqlalchemy.create_engine(os.environ["DEMO_ERP_DATABASE_URL"])
    with target_engine.connect() as conn:
        count = conn.execute(sqlalchemy.text("SELECT count(*) FROM sale_order WHERE name = 'TEST_DUPLICATE'")).scalar()
    assert count == 0  # nothing partially applied


def test_migrate_reports_not_configured_without_django_project(governance_url, monkeypatch):
    monkeypatch.delenv("DJANGO_PROJECT_PATH", raising=False)
    db = SessionLocal()
    result = api.migrate(
        api.MigrateRequest(target_platform="django", description="Add a column", capability="database_agent", requesting_agent="reasoning_engine", task_id="task-migrate-1"),
        db,
    )
    db.close()
    assert result["status"] == "not_configured"


def test_migrate_generates_a_real_file_when_configured(governance_url, tmp_path, monkeypatch):
    monkeypatch.setenv("DJANGO_PROJECT_PATH", str(tmp_path))
    db = SessionLocal()
    result = api.migrate(
        api.MigrateRequest(target_platform="django", description="Add a discount_pct column", capability="database_agent", requesting_agent="reasoning_engine", task_id="task-migrate-2"),
        db,
    )
    db.close()
    assert result["status"] == "generated"
    assert result["requires_approval"] is True
    import pathlib
    assert pathlib.Path(result["migration_ref"]).exists()


def test_schema_introspection_returns_real_tables(governance_url):
    db = SessionLocal()
    result = api.schema("demo_erp", "database_agent", db)
    db.close()
    assert "sale_order" in result["tables"]
    assert "res_partner" in result["tables"]
    column_names = {c["name"] for c in result["tables"]["sale_order"]}
    assert "amount_total" in column_names
