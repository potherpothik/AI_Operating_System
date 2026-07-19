import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text, Boolean
from platform_spine.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


class Task(Base):
    __tablename__ = "task"

    id = Column(String, primary_key=True, default=_uuid)
    correlation_id = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    requested_by = Column(String, nullable=False)
    priority = Column(String, default="normal")
    status = Column(String, default="queued")
    parent_task_id = Column(String, nullable=True)
    agent_capability = Column(String, nullable=True)  # assigned capability, once known (Planner, Phase 8)
    context_refs = Column(Text, default="")  # JSON-encoded list; kept as text for portability across backends
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class TaskEvent(Base):
    __tablename__ = "task_event"

    id = Column(String, primary_key=True, default=_uuid)
    task_id = Column(String, nullable=False)
    from_status = Column(String, nullable=True)
    to_status = Column(String, nullable=False)
    actor = Column(String, nullable=False)
    detail = Column(Text, default="")
    ts = Column(DateTime(timezone=True), default=_now)


class ConfigOverride(Base):
    __tablename__ = "config_override"

    id = Column(String, primary_key=True, default=_uuid)
    service = Column(String, nullable=False)
    key = Column(String, nullable=False)
    value = Column(Text, nullable=False)
    set_by = Column(String, nullable=False)
    set_at = Column(DateTime(timezone=True), default=_now)
    requires_approval = Column(Boolean, default=False)
