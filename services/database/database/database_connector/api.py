import uuid
import time
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import inspect
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from database.db import get_db
from database import clients
from database.database_connector import query_builder, scoping, dry_run, store
from database.database_connector.migration_adapter import create_migration, MigrationNotConfigured, UnknownPlatform
from database.database_connector.pool import get_engine

router = APIRouter(prefix="/db", tags=["database"])

DEFAULT_ROW_LIMIT = 500


class QueryRequest(BaseModel):
    target_db: str
    table: str
    sql_template: str
    params: dict = {}
    capability: str
    requesting_agent: str
    task_id: str = None
    requester_ceiling: str = "internal"
    row_limit: int = DEFAULT_ROW_LIMIT
    correlation_id: str = None


@router.post("/query")
def query(req: QueryRequest, db: Session = Depends(get_db)):
    decision = clients.authorize(req.capability, "db.read", req.target_db, correlation_id=req.correlation_id or "")
    if decision["decision"] != "allow":
        clients.audit_log(req.capability, "db.read", req.target_db, decision="deny", reason=decision.get("reason", ""), correlation_id=req.correlation_id or "")
        raise HTTPException(status_code=403, detail=decision.get("reason", "denied"))

    try:
        query_type = query_builder.classify(req.sql_template)
    except query_builder.UnsupportedStatement as e:
        raise HTTPException(status_code=400, detail=str(e))
    if query_type != "read":
        raise HTTPException(status_code=400, detail=f"/db/query only accepts SELECT statements, got a {query_type!r} statement — use /db/dry_run and /db/write instead")

    try:
        built = query_builder.build(req.sql_template, req.params)
    except query_builder.UnparameterizedQuery as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        engine = get_engine(req.target_db, req.capability, correlation_id=req.correlation_id or "")
    except clients.SecretResolutionFailed as e:
        raise HTTPException(status_code=502, detail=str(e))

    start = time.monotonic()
    try:
        with engine.connect() as conn:
            result = conn.execute(built)
            columns = list(result.keys())
            rows = [dict(zip(columns, r)) for r in result.fetchmany(req.row_limit + 1)]
    except DBAPIError as e:
        clients.audit_log(req.capability, "db.read", req.target_db, decision="failed", reason=str(e.orig), correlation_id=req.correlation_id or "")
        raise HTTPException(status_code=400, detail=f"query failed: {e.orig}")
    duration_ms = int((time.monotonic() - start) * 1000)

    truncated = len(rows) > req.row_limit
    rows = rows[: req.row_limit]

    allowed_columns, denied_columns = scoping.filter_columns(req.target_db, req.table, columns, req.requester_ceiling)
    redacted_rows = [{k: v for k, v in row.items() if k in allowed_columns} for row in rows]

    store.log_query(db, req.task_id, req.capability, req.target_db, "read", req.sql_template, len(redacted_rows), duration_ms)
    clients.audit_log(req.capability, "db.read", f"{req.target_db}.{req.table}", decision="completed", reason=f"rows={len(redacted_rows)}", correlation_id=req.correlation_id or "")

    return {"rows": redacted_rows, "row_count": len(redacted_rows), "columns": allowed_columns, "redacted_columns": denied_columns, "truncated": truncated}


class DryRunRequest(BaseModel):
    target_db: str
    sql_template: str
    params: dict = {}
    capability: str
    requesting_agent: str
    task_id: str = None
    correlation_id: str = None


@router.post("/dry_run")
def dry_run_endpoint(req: DryRunRequest, db: Session = Depends(get_db)):
    decision = clients.authorize(req.capability, "db.dry_run", req.target_db, correlation_id=req.correlation_id or "")
    if decision["decision"] != "allow":
        clients.audit_log(req.capability, "db.dry_run", req.target_db, decision="deny", reason=decision.get("reason", ""), correlation_id=req.correlation_id or "")
        raise HTTPException(status_code=403, detail=decision.get("reason", "denied"))

    try:
        engine = get_engine(req.target_db, req.capability, correlation_id=req.correlation_id or "")
    except clients.SecretResolutionFailed as e:
        raise HTTPException(status_code=502, detail=str(e))

    try:
        estimate = dry_run.estimate(engine, req.sql_template, req.params)
    except (query_builder.UnparameterizedQuery, query_builder.UnsupportedStatement, dry_run.DryRunFailed) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DBAPIError as e:
        # A bad dry-run is exactly what dry-run is FOR catching — a
        # statement that would fail against the real schema never gets
        # anywhere near /db/write, since it can never produce a dry_run_id
        # to reference.
        clients.audit_log(req.capability, "db.dry_run", req.target_db, decision="failed", reason=str(e.orig), correlation_id=req.correlation_id or "")
        raise HTTPException(status_code=400, detail=f"dry-run failed: {e.orig}")

    row = store.create_dry_run(db, req.task_id, req.target_db, req.sql_template, req.params, estimate["estimated_rows_affected"])
    clients.audit_log(req.capability, "db.dry_run", req.target_db, decision="completed", reason=f"estimated_rows={estimate['estimated_rows_affected']}", correlation_id=req.correlation_id or "")

    return {"dry_run_id": row.id, "estimated_rows_affected": estimate["estimated_rows_affected"], "plan_node_type": estimate["plan_node_type"]}


class WriteRequest(BaseModel):
    target_db: str
    sql_template: str
    params: dict = {}
    dry_run_id: str
    capability: str
    requesting_agent: str
    task_id: str = None
    correlation_id: str = None


@router.post("/write")
def write(req: WriteRequest, db: Session = Depends(get_db)):
    # Dry-run isn't advisory, it's a structural precondition (Phase 7
    # doc, failure handling) — a write without a valid, matching
    # dry-run reference is rejected outright, before authorization is
    # even checked.
    dry = store.get_dry_run(db, req.dry_run_id)
    if not dry:
        raise HTTPException(status_code=400, detail=f"no dry-run found for dry_run_id {req.dry_run_id!r} — a write always requires a preceding dry-run")
    if not store.dry_run_matches(dry, req.sql_template, req.params):
        raise HTTPException(status_code=400, detail="this write's template/params do not match what was previewed in the referenced dry-run — no drift allowed between preview and execution")

    decision = clients.authorize(req.capability, "db.write", req.target_db, correlation_id=req.correlation_id or "")
    if decision["decision"] != "allow":
        clients.audit_log(req.capability, "db.write", req.target_db, decision="deny", reason=decision.get("reason", ""), correlation_id=req.correlation_id or "")
        raise HTTPException(status_code=403, detail=decision.get("reason", "denied"))

    try:
        built = query_builder.build(req.sql_template, req.params)
    except query_builder.UnparameterizedQuery as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        engine = get_engine(req.target_db, req.capability, correlation_id=req.correlation_id or "")
    except clients.SecretResolutionFailed as e:
        raise HTTPException(status_code=502, detail=str(e))

    write_row = store.create_write(db, req.task_id, req.dry_run_id)
    transaction_id = str(uuid.uuid4())
    start = time.monotonic()

    try:
        with engine.begin() as conn:  # commits on clean exit, rolls back automatically on exception
            result = conn.execute(built)
            actual_rows = result.rowcount
    except Exception as e:  # noqa: BLE001 — any failure mid-transaction: confirm rollback, never assume it, before reporting failed
        # engine.begin()'s context manager already issued the rollback on
        # exception exit — confirm the connection pool is actually usable
        # again (not left holding a broken transaction) before reporting
        # "failed" rather than just trusting the context manager silently
        # did the right thing.
        with engine.connect() as verify_conn:
            from sqlalchemy import text as _text
            verify_conn.execute(_text("SELECT 1"))
        finalized = store.finalize_write(db, write_row.id, "failed", rolled_back=True)
        clients.audit_log(
            req.capability, "db.write", req.target_db, decision="failed",
            reason=f"dry_run_estimate={dry.estimated_rows_affected}, error={e}", correlation_id=req.correlation_id or "",
        )
        raise HTTPException(status_code=500, detail=f"write failed and was rolled back: {e}")

    duration_ms = int((time.monotonic() - start) * 1000)
    finalized = store.finalize_write(db, write_row.id, "completed", actual_rows_affected=actual_rows, transaction_id=transaction_id)
    store.log_query(db, req.task_id, req.capability, req.target_db, "write", req.sql_template, actual_rows, duration_ms)

    # Estimate and actual outcome logged side by side, per Phase 7 doc.
    clients.audit_log(
        req.capability, "db.write", req.target_db, decision="completed",
        reason=f"dry_run_estimate={dry.estimated_rows_affected}, actual_rows={actual_rows}", correlation_id=req.correlation_id or "",
    )

    return {
        "write_id": finalized.id, "transaction_id": transaction_id,
        "affected_rows_estimate": dry.estimated_rows_affected, "actual_rows_affected": actual_rows, "status": "completed",
    }


class MigrateRequest(BaseModel):
    target_platform: str  # django | odoo
    description: str
    capability: str
    requesting_agent: str
    task_id: str
    correlation_id: str = None


@router.post("/migrate")
def migrate(req: MigrateRequest, db: Session = Depends(get_db)):
    decision = clients.authorize(req.capability, "db.migrate", req.target_platform, correlation_id=req.correlation_id or "")
    if decision["decision"] != "allow":
        clients.audit_log(req.capability, "db.migrate", req.target_platform, decision="deny", reason=decision.get("reason", ""), correlation_id=req.correlation_id or "")
        raise HTTPException(status_code=403, detail=decision.get("reason", "denied"))

    request_row = store.create_migration_request(db, req.task_id, req.target_platform)

    try:
        result = create_migration(req.target_platform, req.task_id, req.description)
    except MigrationNotConfigured as e:
        finalized = store.finalize_migration_request(db, request_row.id, "not_configured")
        clients.audit_log(req.capability, "db.migrate", req.target_platform, decision="not_configured", reason=str(e), correlation_id=req.correlation_id or "")
        return {"id": finalized.id, "status": "not_configured", "reason": str(e)}
    except UnknownPlatform as e:
        raise HTTPException(status_code=400, detail=str(e))

    finalized = store.finalize_migration_request(db, request_row.id, "generated", migration_ref=result["migration_ref"])
    clients.audit_log(req.capability, "db.migrate", req.target_platform, decision="generated", reason=result["migration_ref"], correlation_id=req.correlation_id or "")

    return {"id": finalized.id, "status": "generated", "migration_ref": result["migration_ref"], "requires_approval": True}


@router.get("/schema/{target}")
def schema(target: str, capability: str, db: Session = Depends(get_db)):
    decision = clients.authorize(capability, "db.read", target)
    if decision["decision"] != "allow":
        raise HTTPException(status_code=403, detail=decision.get("reason", "denied"))

    try:
        engine = get_engine(target, capability)
    except clients.SecretResolutionFailed as e:
        raise HTTPException(status_code=502, detail=str(e))

    inspector = inspect(engine)
    tables = {}
    for table_name in inspector.get_table_names():
        tables[table_name] = [
            {"name": c["name"], "type": str(c["type"])} for c in inspector.get_columns(table_name)
        ]
    return {"target_db": target, "tables": tables}
