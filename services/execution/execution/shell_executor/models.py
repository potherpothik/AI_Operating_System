import uuid
import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, JSON

from execution.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class SandboxExecution(Base):
    __tablename__ = "sandbox_execution"

    id = Column(String, primary_key=True, default=_uuid)
    task_id = Column(String, nullable=True)
    requesting_capability = Column(String, nullable=False)
    command = Column(String, nullable=False)
    args = Column(JSON, nullable=False)
    working_dir = Column(String, nullable=False)
    mode = Column(String, nullable=False)  # read_only | mutating
    status = Column(String, default="running")  # running | completed | timed_out | failed | killed
    exit_code = Column(Integer, nullable=True)
    stdout = Column(Text, nullable=True)
    stderr = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    backend = Column(String, nullable=True)
    correlation_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)
