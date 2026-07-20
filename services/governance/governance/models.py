import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text, Boolean
from governance.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


class AuditEvent(Base):
    """Append-only. prev_hash/this_hash form a hash chain — see audit/store.py."""

    __tablename__ = "audit_event"

    id = Column(String, primary_key=True, default=_uuid)
    # timezone=True -> Postgres TIMESTAMPTZ: stores the real UTC instant
    # regardless of session timezone. Without it, a non-UTC session
    # silently shifts the stored wall-clock value — confirmed by direct
    # testing, not assumed.
    ts = Column(DateTime(timezone=True), default=_now)
    ts_iso = Column(String, nullable=False)  # exact string the hash was computed from — see audit/store.py
    actor_id = Column(String, nullable=False)
    actor_type = Column(String, nullable=False)
    action = Column(String, nullable=False)
    resource = Column(String, nullable=False)
    decision = Column(String, nullable=False)
    reason = Column(Text, default="")
    context_hash = Column(String, default="")
    correlation_id = Column(String, default="")
    prev_hash = Column(String, default="")
    this_hash = Column(String, nullable=False)


class ApprovalRequest(Base):
    __tablename__ = "approval_request"

    id = Column(String, primary_key=True, default=_uuid)
    action = Column(String, nullable=False)
    risk_tier = Column(String, default="medium")
    requested_by = Column(String, nullable=False)
    payload_ref = Column(Text, default="")
    status = Column(String, default="pending")  # pending | approved | rejected | expired
    created_at = Column(DateTime(timezone=True), default=_now)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    decided_by = Column(String, nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    comment = Column(Text, default="")


class ApprovalReview(Base):
    """
    Phase 16: a second agent's structured input attached to another
    agent's pending approval — Code Review Agent's own advisory
    assessment, additional context for the human approver, never a
    decision itself. Append-only, same posture as AuditEvent above: a
    review is never edited or deleted, only added. No real foreign-key
    constraint to approval_request.id, same posture as every other
    cross-table reference in this codebase.
    """

    __tablename__ = "approval_review"

    id = Column(String, primary_key=True, default=_uuid)
    approval_id = Column(String, nullable=False)
    reviewer_capability = Column(String, nullable=False)
    verdict = Column(String, nullable=False)  # concern | recommend_approve
    reasoning = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), default=_now)


class TestExecutionTarget(Base):
    """
    Phase 10: Testing Agent's environment-target verification record — a
    genuinely new safety question beyond classification (what CONTENT is
    this, per every prior agent) — which ENVIRONMENT does this even point
    at. One row per verification decision, so "did we actually check
    before this run" is always answerable, the same audit posture as
    every approval/secret decision elsewhere in governance.
    """

    __tablename__ = "test_execution_target"

    id = Column(String, primary_key=True, default=_uuid)
    capability = Column(String, nullable=False)
    resolved_environment = Column(String, nullable=False)
    is_sandbox = Column(Boolean, nullable=False)
    verified_by_security_layer = Column(String, nullable=False)  # "allow" | "deny"
    ts = Column(DateTime(timezone=True), default=_now)
