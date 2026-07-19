import uuid
import datetime
from sqlalchemy import Column, String, DateTime, JSON

from execution.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class GitAction(Base):
    __tablename__ = "git_action"

    id = Column(String, primary_key=True, default=_uuid)
    task_id = Column(String, nullable=True)
    reasoning_execution_id = Column(String, nullable=True)
    context_id = Column(String, nullable=True)
    action = Column(String, nullable=False)  # branch | commit | diff | push | open_mr
    repo = Column(String, nullable=False)
    agent_capability = Column(String, nullable=False)
    branch_name = Column(String, nullable=True)
    commit_sha = Column(String, nullable=True)
    mr_ref = Column(String, nullable=True)
    provenance_trailer = Column(String, nullable=True)
    result = Column(JSON, nullable=True)
    status = Column(String, default="completed")  # completed | failed
    created_at = Column(DateTime(timezone=True), default=_now)
