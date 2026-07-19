import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text, Boolean

from assembly.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


class PromptTemplate(Base):
    __tablename__ = "prompt_template"

    id = Column(String, primary_key=True, default=_uuid)
    agent_template_id = Column(String, nullable=False, index=True)
    version = Column(String, default="1")
    body = Column(Text, nullable=False)  # a Python format-string; {context}, {task}, etc.
    expected_output_schema = Column(Text, nullable=False)  # JSON-encoded field->type spec
    status = Column(String, default="active")  # pending_approval | active | rejected
    approval_id = Column(String, nullable=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)


class PromptRenderLog(Base):
    __tablename__ = "prompt_render_log"

    id = Column(String, primary_key=True, default=_uuid)
    context_package_id = Column(String, nullable=False, index=True)
    template_id = Column(String, nullable=False)
    template_version = Column(String, nullable=False)
    target_model = Column(String, nullable=False)
    rendered_at = Column(DateTime(timezone=True), default=_now)
