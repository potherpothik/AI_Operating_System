import uuid
import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, JSON

from extensibility.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class Plugin(Base):
    """
    capability_yaml/template_md are the plugin's actual manifest content
    — the same two files any built-in agent under services/agents/agents/
    has, just submitted over HTTP instead of committed to this repo.
    Stored here as the durable record; installer.py writes them to a
    real file (capability.yaml) the agents service discovers, and
    registers the template with Prompt Builder — the two steps that
    actually make an approved plugin runnable.
    """

    __tablename__ = "plugin"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False, unique=True)
    version = Column(String, default="1")
    capability_yaml = Column(Text, nullable=False)
    template_md = Column(Text, nullable=False)
    expected_output_schema = Column(JSON, nullable=True)  # defaults to the shared 6-field schema + action if omitted
    declared_capabilities = Column(JSON, default=list)  # informational — the action names this plugin's own capability.yaml declares
    required_permissions = Column(JSON, default=list)  # existing system actions this plugin's capability needs (e.g. "shell.execute")
    status = Column(String, default="pending_approval")  # pending_approval | active | disabled | rejected
    installed_by = Column(String, nullable=False)
    approval_id = Column(String, nullable=True)
    error_count = Column(Integer, default=0)
    installed_at = Column(DateTime(timezone=True), default=_now)
    decided_at = Column(DateTime(timezone=True), nullable=True)
