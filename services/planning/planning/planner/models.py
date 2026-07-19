import uuid
import datetime
from sqlalchemy import Column, String, Float, Boolean, Text, DateTime, JSON

from planning.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class TaskGraph(Base):
    __tablename__ = "task_graph"

    id = Column(String, primary_key=True, default=_uuid)
    task_id = Column(String, nullable=False)
    planning_confidence = Column(Float, nullable=True)
    needs_clarification = Column(Boolean, default=False)
    clarification_question = Column(Text, nullable=True)
    outcome = Column(String, nullable=False)  # plan | needs_clarification | no_capability_found | failed
    reasoning_execution_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    superseded_by = Column(String, nullable=True)


class Subtask(Base):
    __tablename__ = "subtask"

    id = Column(String, primary_key=True, default=_uuid)
    task_graph_id = Column(String, nullable=False)
    subtask_id = Column(String, nullable=False)  # the model's own short id, e.g. "s1" — scoped to its graph
    description = Column(Text, nullable=False)
    agent_capability = Column(String, nullable=False)
    depends_on = Column(JSON, nullable=False, default=list)  # list of subtask_id strings
    status = Column(String, default="planned")  # planned | queued | in_progress | done | failed
    platform_task_id = Column(String, nullable=True)  # the real Task Manager task this subtask became
