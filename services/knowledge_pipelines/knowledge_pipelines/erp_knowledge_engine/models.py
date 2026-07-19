import uuid
import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, JSON

from knowledge_pipelines.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class ErpSchemaSnapshot(Base):
    __tablename__ = "erp_schema_snapshot"

    id = Column(String, primary_key=True, default=_uuid)
    target_db = Column(String, nullable=False)
    synced_at = Column(DateTime(timezone=True), default=_now)
    module_count = Column(Integer, default=1)  # this environment has no live Odoo instance with real module boundaries — see README
    model_count = Column(Integer, nullable=False)
    tables = Column(JSON, nullable=False)  # the raw {table: {columns, foreign_keys}} snapshot, for graph.py to query
    status = Column(String, default="current")  # current | stale


class ErpFieldAnnotation(Base):
    __tablename__ = "erp_field_annotation"

    id = Column(String, primary_key=True, default=_uuid)
    model_name = Column(String, nullable=False)
    field_name = Column(String, nullable=False)
    business_meaning = Column(Text, nullable=False)
    annotated_by = Column(String, nullable=False)
    annotated_at = Column(DateTime(timezone=True), default=_now)
    classification = Column(String, default="internal")


class ErpFormula(Base):
    __tablename__ = "erp_formula"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    formula_ref = Column(Text, nullable=False)
    business_purpose = Column(Text, nullable=False)
    classification = Column(String, default="internal")
    defined_by = Column(String, nullable=False)
    version = Column(String, default="1")
    status = Column(String, default="active")  # active | superseded
    superseded_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
