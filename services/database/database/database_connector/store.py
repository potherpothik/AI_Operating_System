import datetime
from sqlalchemy.orm import Session

from database.database_connector.models import DbQueryLog, DbDryRun, DbWrite, DbMigrationRequest, hash_template, hash_params


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def log_query(db: Session, task_id: str, capability: str, target_db: str, query_type: str,
              sql_template: str, row_count: int, duration_ms: int, target_schema: str = None) -> DbQueryLog:
    row = DbQueryLog(
        task_id=task_id, capability=capability, target_db=target_db, target_schema=target_schema,
        query_type=query_type, query_template_hash=hash_template(sql_template),
        row_count=row_count, duration_ms=duration_ms,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def create_dry_run(db: Session, task_id: str, target_db: str, sql_template: str, params: dict,
                    estimated_rows_affected: int, columns_touched: list = None) -> DbDryRun:
    row = DbDryRun(
        task_id=task_id, target_db=target_db, query_template_hash=hash_template(sql_template),
        params_hash=hash_params(params), estimated_rows_affected=estimated_rows_affected,
        columns_touched=columns_touched or [],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_dry_run(db: Session, dry_run_id: str) -> DbDryRun | None:
    return db.query(DbDryRun).filter(DbDryRun.id == dry_run_id).first()


def dry_run_matches(dry_run: DbDryRun, sql_template: str, params: dict) -> bool:
    """No drift between preview and execution (Phase 7 doc, Section 3) —
    the write's template and params must hash to exactly what was
    previewed, not merely reference the same dry_run_id."""
    return dry_run.query_template_hash == hash_template(sql_template) and dry_run.params_hash == hash_params(params)


def create_write(db: Session, task_id: str, dry_run_id: str) -> DbWrite:
    row = DbWrite(task_id=task_id, dry_run_id=dry_run_id, status="pending")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def finalize_write(db: Session, write_id: str, status: str, actual_rows_affected: int = None,
                    transaction_id: str = None, rolled_back: bool = False) -> DbWrite | None:
    row = db.query(DbWrite).filter(DbWrite.id == write_id).first()
    if not row:
        return None
    row.status = status
    row.actual_rows_affected = actual_rows_affected
    row.transaction_id = transaction_id
    row.rolled_back = rolled_back
    row.executed_at = _now()
    db.commit()
    db.refresh(row)
    return row


def create_migration_request(db: Session, task_id: str, target_platform: str) -> DbMigrationRequest:
    row = DbMigrationRequest(task_id=task_id, target_platform=target_platform, requires_approval=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def finalize_migration_request(db: Session, request_id: str, status: str, migration_ref: str = None, approved_by: str = None) -> DbMigrationRequest | None:
    row = db.query(DbMigrationRequest).filter(DbMigrationRequest.id == request_id).first()
    if not row:
        return None
    row.status = status
    row.migration_ref = migration_ref
    row.approved_by = approved_by
    if status == "applied":
        row.applied_at = _now()
    db.commit()
    db.refresh(row)
    return row
