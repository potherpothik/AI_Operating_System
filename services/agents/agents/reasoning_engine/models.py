import uuid
import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, JSON

from agents.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class ReasoningExecution(Base):
    __tablename__ = "reasoning_execution"

    id = Column(String, primary_key=True, default=_uuid)
    task_id = Column(String, nullable=False)
    context_id = Column(String, nullable=True)
    agent_capability = Column(String, nullable=False)
    target_model = Column(String, nullable=False)
    status = Column(String, default="in_progress")  # in_progress|completed|refused|awaiting_approval|awaiting_delegation|rejected|failed
    result = Column(JSON, nullable=True)
    approval_id = Column(String, nullable=True)
    delegate_task_id = Column(String, nullable=True)
    failure_reason = Column(Text, nullable=True)
    iterations_used = Column(Integer, default=0)
    max_iterations = Column(Integer, default=8)
    correlation_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class ReasoningStep(Base):
    __tablename__ = "reasoning_step"

    id = Column(String, primary_key=True, default=_uuid)
    execution_id = Column(String, nullable=False)
    iteration = Column(Integer, nullable=False)
    prompt_ref = Column(String, nullable=True)  # render_log_id from Prompt Builder
    raw_response = Column(Text, nullable=True)
    parsed_decision = Column(JSON, nullable=True)
    routing_outcome = Column(String, nullable=True)
    ts = Column(DateTime(timezone=True), default=_now)


class AgentCapabilityDef(Base):
    __tablename__ = "agent_capability_def"

    agent_capability = Column(String, primary_key=True)
    allowed_actions = Column(JSON, nullable=False)
    forbidden_actions = Column(JSON, nullable=False)
    requires_approval = Column(JSON, nullable=False)
    classification_ceiling = Column(String, nullable=False)
    template_id = Column(String, nullable=False)
