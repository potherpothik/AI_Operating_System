import uuid
import datetime
from sqlalchemy import Column, String, Integer, DateTime, JSON

from observability.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class AlertConfig(Base):
    """
    Persists the intent to alert — no real notification channel exists
    in this codebase (no email/Slack/webhook integration anywhere), so
    this is honestly an "offline-capable" hook: a human polls
    GET /health/system today, the same way a human already polls
    GET /approval/pending for Human Approval Layer. See the design doc's
    Section 5 for why this isn't silently claimed to send anything.
    """

    __tablename__ = "alert_config"

    id = Column(String, primary_key=True, default=_uuid)
    metric_or_gap = Column(String, nullable=False)  # e.g. "stuck_tasks", "governance_unreachable"
    threshold = Column(Integer, nullable=True)  # meaning depends on metric_or_gap (e.g. minutes, count)
    destination_ref = Column(String, nullable=False)  # a description of where an alert would go — never sent anywhere in this phase
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)


class HealthPollLog(Base):
    __tablename__ = "health_poll_log"

    id = Column(String, primary_key=True, default=_uuid)
    polled_at = Column(DateTime(timezone=True), default=_now)
    services_down = Column(JSON, default=list)
    gaps_found = Column(JSON, default=list)
