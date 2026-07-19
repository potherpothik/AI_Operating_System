import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text, Integer, Boolean

from assembly.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


class ContextPackage(Base):
    __tablename__ = "context_package"

    id = Column(String, primary_key=True, default=_uuid)
    task_id = Column(String, nullable=False, index=True)
    agent_capability = Column(String, nullable=False)
    target_model = Column(String, nullable=False)
    classification_ceiling = Column(String, nullable=False)
    budget_used = Column(Integer, default=0)
    budget_total = Column(Integer, default=0)
    partial = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_now)


class ContextItem(Base):
    __tablename__ = "context_item"

    id = Column(String, primary_key=True, default=_uuid)
    context_package_id = Column(String, nullable=False, index=True)
    source_type = Column(String, nullable=False)  # memory | vector | pinned | explicit_ref
    source_id = Column(String, default="")
    content = Column(Text, nullable=False)
    provenance = Column(Text, default="")
    included_reason = Column(String, default="")  # top-k relevance | pinned | recency


class PinnedFact(Base):
    """Facts a human has explicitly pinned to always include for a namespace/capability pair."""

    __tablename__ = "pinned_fact"

    id = Column(String, primary_key=True, default=_uuid)
    namespace = Column(String, nullable=False, index=True)
    agent_capability = Column(String, nullable=True)  # null = applies to all capabilities in the namespace
    content = Column(Text, nullable=False)
    pinned_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)
