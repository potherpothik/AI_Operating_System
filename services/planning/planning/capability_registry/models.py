import uuid
import datetime
from sqlalchemy import Column, String, DateTime, JSON

from planning.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class CapabilityRegistryEntry(Base):
    __tablename__ = "capability_registry_entry"

    id = Column(String, primary_key=True, default=_uuid)
    agent_capability = Column(String, nullable=False)
    version = Column(String, nullable=False, default="1")
    allowed_actions = Column(JSON, nullable=False)
    forbidden_actions = Column(JSON, nullable=False)
    requires_approval = Column(JSON, nullable=False)
    classification_ceiling = Column(String, nullable=False)
    status = Column(String, default="active")  # active | pending_approval | deprecated | rejected
    approval_id = Column(String, nullable=True)
    registered_at = Column(DateTime(timezone=True), default=_now)
    deprecated_at = Column(DateTime(timezone=True), nullable=True)
