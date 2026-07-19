import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text, Boolean
from knowledge.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


class MemoryRecord(Base):
    __tablename__ = "memory_record"

    id = Column(String, primary_key=True, default=_uuid)
    memory_type = Column(String, nullable=False, index=True)
    namespace = Column(String, nullable=False, index=True)  # project_id, or "global" for user-scoped types
    key = Column(String, nullable=False, index=True)
    value = Column(Text, nullable=False)  # JSON-encoded
    classification = Column(String, default="internal")
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)
    ttl_expires_at = Column(DateTime(timezone=True), nullable=True)
    superseded_by = Column(String, nullable=True)

    # Only meaningful for requires_approval_to_write types (business_memory):
    status = Column(String, default="active")  # active | pending_approval | rejected
    approval_id = Column(String, nullable=True)


class DecisionRecord(Base):
    """Backing store for decision_history / architecture_history — append-only."""

    __tablename__ = "decision_record"

    id = Column(String, primary_key=True, default=_uuid)
    namespace = Column(String, nullable=False, index=True)
    memory_type = Column(String, nullable=False)  # decision_history | architecture_history
    title = Column(String, nullable=False)
    rationale = Column(Text, default="")
    alternatives_considered = Column(Text, default="")
    decided_by = Column(String, nullable=False)
    decided_at = Column(DateTime(timezone=True), default=_now)
    supersedes_id = Column(String, nullable=True)
