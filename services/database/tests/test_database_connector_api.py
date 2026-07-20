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


def test_query_log_lists_real_recorded_queries_filtered_by_capability(governance_url):
    """Phase 13: GET /db/query-log is the listing endpoint Metrics
    Dashboard's tool-execution-volume-by-capability category needs —
    no listing endpoint existed before this, only the write path that
    populates the table on every real query."""
    db = SessionLocal()
    api.query(
        api.QueryRequest(
            target_db="demo_erp", table="sale_order",
            sql_template="SELECT id, name FROM sale_order WHERE partner_id = :partner_id ORDER BY id",
            params={"partner_id": 1}, capability="database_agent", requesting_agent="reasoning_engine",
        ),
        db,
    )
    rows = api.query_log(capability="database_agent", db=db)
    db.close()

    assert len(rows) >= 1
    assert all(r["capability"] == "database_agent" for r in rows)
    assert rows[0]["target_db"] == "demo_erp"
    assert rows[0]["query_type"] == "read"


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


def test_confidential_ceiling_alone_no_longer_reveals_the_pii_tagged_column(governance_url):
    """
    Pre-Phase-15 behavior: a confidential ceiling alone was sufficient to
    see res_partner.email, since it was just the top of the single
    classification scale. Phase 15 makes PII a second, orthogonal
    dimension (scoping.filter_pii_columns) — email is BOTH
    confidential-tier AND PII-tagged, so clearing the ceiling is no
    longer enough on its own; see test_query_pii_field_requested_by_authorized_capability_includes_real_value
    below for what actually is required.
    """
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
    assert "email" not in result["rows"][0]
    assert "email" in result["redacted_columns"]


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


# ---------------------------------------------------------------------------
# Phase 15 — PII dimension, orthogonal to the classification ceiling above.
# ---------------------------------------------------------------------------

def test_query_pii_field_silently_excluded_when_not_requested(governance_url):
    """Even a capability with no PII involvement at all gets the normal,
    silent exclusion (same as any other denied column) when it doesn't
    ask for a PII field — no 403, this isn't a failure, just the
    ceiling-style default."""
    db = SessionLocal()
    result = api.query(
        api.QueryRequest(
            target_db="demo_erp", table="res_partner",
            sql_template="SELECT id, name, email FROM res_partner WHERE id = :id",
            params={"id": 1}, capability="sales_agent", requesting_agent="reasoning_engine",
            requester_ceiling="confidential",
        ),
        db,
    )
    db.close()
    assert "email" not in result["columns"]
    assert "email" in result["redacted_columns"]


def test_query_pii_field_requested_by_unregistered_capability_is_refused(governance_url):
    """database_agent isn't on demo_erp's PII authorized_capabilities list
    (only sales_agent is, per pii_registry.yaml) — requesting a PII field
    anyway is a real 403, not a silent redaction."""
    db = SessionLocal()
    with pytest.raises(HTTPException) as exc_info:
        api.query(
            api.QueryRequest(
                target_db="demo_erp", table="res_partner",
                sql_template="SELECT id, name, email FROM res_partner WHERE id = :id",
                params={"id": 1}, capability="database_agent", requesting_agent="reasoning_engine",
                requester_ceiling="confidential", pii_fields_requested=["email"],
            ),
            db,
        )
    db.close()
    assert exc_info.value.status_code == 403


def test_query_pii_field_requested_by_authorized_capability_includes_real_value(governance_url):
    """sales_agent IS on the registry's allow-list and governance's role
    grants db.read_pii — explicitly naming the field is the only way to
    actually get it back, confirmed against the real seeded value."""
    db = SessionLocal()
    result = api.query(
        api.QueryRequest(
            target_db="demo_erp", table="res_partner",
            sql_template="SELECT id, name, email FROM res_partner WHERE id = :id",
            params={"id": 1}, capability="sales_agent", requesting_agent="reasoning_engine",
            requester_ceiling="confidential", pii_fields_requested=["email"],
        ),
        db,
    )
    db.close()
    assert "email" in result["columns"]
    assert result["rows"][0]["email"] == "ops@acme.example"


def test_query_pii_field_still_excluded_at_confidential_ceiling_when_not_named(governance_url):
    """The whole point of the second, orthogonal gate: even sales_agent,
    even at a confidential ceiling, doesn't get email back unless this
    SPECIFIC request named it — clearing the ceiling isn't enough on its
    own."""
    db = SessionLocal()
    result = api.query(
        api.QueryRequest(
            target_db="demo_erp", table="res_partner",
            sql_template="SELECT id, name, email FROM res_partner WHERE id = :id",
            params={"id": 1}, capability="sales_agent", requesting_agent="reasoning_engine",
            requester_ceiling="confidential", pii_fields_requested=[],
        ),
        db,
    )
    db.close()
    assert "email" not in result["columns"]
    assert "email" in result["redacted_columns"]


def test_schema_introspection_returns_real_tables(governance_url):
    db = SessionLocal()
    result = api.schema("demo_erp", "database_agent", db)
    db.close()
    assert "sale_order" in result["tables"]
    assert "res_partner" in result["tables"]
    column_names = {c["name"] for c in result["tables"]["sale_order"]["columns"]}
    assert "amount_total" in column_names


def test_schema_introspection_includes_real_foreign_keys(governance_url):
    """sale_order.partner_id genuinely references res_partner.id in the
    seeded demo_erp schema — this isn't invented data, it's a real FK
    constraint, introspected the same way Phase 9's ERP Knowledge Engine
    will consume it for its structured relationship graph."""
    db = SessionLocal()
    result = api.schema("demo_erp", "database_agent", db)
    db.close()
    fks = result["tables"]["sale_order"]["foreign_keys"]
    assert len(fks) == 1
    assert fks[0]["references_table"] == "res_partner"
    assert "partner_id" in fks[0]["columns"]
