import uuid
import datetime
from sqlalchemy import Column, String, Boolean, DateTime

from knowledge_pipelines.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class DocSource(Base):
    __tablename__ = "doc_source"

    id = Column(String, primary_key=True, default=_uuid)
    source_type = Column(String, nullable=False)  # file | url
    path_or_url = Column(String, nullable=False)
    doc_type = Column(String, nullable=True)
    project_id = Column(String, nullable=False)
    watch_enabled = Column(Boolean, default=False)
    content_hash = Column(String, nullable=True)
    document_id = Column(String, nullable=True)  # Vector Search's own document id, for reindex
    last_ingested_at = Column(DateTime(timezone=True), nullable=True)
    last_status = Column(String, nullable=True)  # completed | failed | stale


class DocIngestionLog(Base):
    __tablename__ = "doc_ingestion_log"

    id = Column(String, primary_key=True, default=_uuid)
    doc_source_id = Column(String, nullable=False)
    document_id = Column(String, nullable=True)
    classification_assigned = Column(String, nullable=True)
    classification_is_default = Column(Boolean, default=False)
    status = Column(String, nullable=False)  # completed | failed
    failure_reason = Column(String, nullable=True)
    ts = Column(DateTime(timezone=True), default=_now)
