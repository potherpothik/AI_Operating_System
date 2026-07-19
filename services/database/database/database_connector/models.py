import uuid
import datetime
import hashlib
from sqlalchemy import Column, String, Integer, Boolean, DateTime, JSON

from database.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def hash_template(sql_template: str) -> str:
    return hashlib.sha256(sql_template.encode()).hexdigest()[:16]


def hash_params(params: dict) -> str:
    import json
    return hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()[:16]


class DbQueryLog(Base):
    __tablename__ = "db_query_log"

    id = Column(String, primary_key=True, default=_uuid)
    task_id = Column(String, nullable=True)
    capability = Column(String, nullable=False)
    target_db = Column(String, nullable=False)
    target_schema = Column(String, nullable=True)
    query_type = Column(String, nullable=False)  # read | write | ddl
    query_template_hash = Column(String, nullable=False)
    row_count = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    ts = Column(DateTime(timezone=True), default=_now)


class DbDryRun(Base):
    __tablename__ = "db_dry_run"

    id = Column(String, primary_key=True, default=_uuid)
    task_id = Column(String, nullable=True)
    target_db = Column(String, nullable=False)
    query_template_hash = Column(String, nullable=False)
    params_hash = Column(String, nullable=False)
    estimated_rows_affected = Column(Integer, nullable=False)
    columns_touched = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)


class DbWrite(Base):
    __tablename__ = "db_write"

    id = Column(String, primary_key=True, default=_uuid)
    task_id = Column(String, nullable=True)
    dry_run_id = Column(String, nullable=False)
    transaction_id = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending | completed | failed | rolled_back
    actual_rows_affected = Column(Integer, nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    rolled_back = Column(Boolean, default=False)


class DbMigrationRequest(Base):
    __tablename__ = "db_migration_request"

    id = Column(String, primary_key=True, default=_uuid)
    task_id = Column(String, nullable=True)
    target_platform = Column(String, nullable=False)  # django | odoo
    migration_ref = Column(String, nullable=True)
    requires_approval = Column(Boolean, default=True)
    approved_by = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending | applied | not_configured | failed
    applied_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
