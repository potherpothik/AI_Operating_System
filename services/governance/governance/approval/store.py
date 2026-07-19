from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from governance.models import ApprovalRequest


def _now_matching(reference: datetime) -> datetime:
    """
    SQLite returns naive datetimes on read even when a tz-aware value was
    stored (Postgres round-trips tz-awareness natively). Compare on the
    same footing as whatever came back from this particular backend.
    """
    now = datetime.now(timezone.utc)
    if reference is not None and reference.tzinfo is None:
        return now.replace(tzinfo=None)
    return now


def create_request(
    db: Session,
    action: str,
    requested_by: str,
    risk_tier: str = "medium",
    payload_ref: str = "",
    ttl_minutes: int = 1440,
) -> ApprovalRequest:
    req = ApprovalRequest(
        action=action,
        requested_by=requested_by,
        risk_tier=risk_tier,
        payload_ref=payload_ref,
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes),
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def decide(db: Session, request_id: str, decided_by: str, approve: bool, comment: str = ""):
    req = db.query(ApprovalRequest).filter(ApprovalRequest.id == request_id).first()
    if not req:
        return None
    if req.status != "pending":
        return req  # already decided or expired — never overwrite a settled decision

    if req.expires_at and _now_matching(req.expires_at) > req.expires_at:
        req.status = "expired"
    else:
        req.status = "approved" if approve else "rejected"
        req.decided_by = decided_by
        req.decided_at = datetime.now(timezone.utc)
        req.comment = comment

    db.commit()
    db.refresh(req)
    return req


def expire_stale(db: Session) -> int:
    # This comparison is compiled into SQL and run by the DB engine, not
    # Python — SQLite stores naive datetimes as text, so an aware "now"
    # with a +00:00 suffix would compare incorrectly against them. Use the
    # naive form here; every expires_at written by create_request() above
    # started as UTC, so naive-vs-naive is an apples-to-apples comparison.
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    stale = (
        db.query(ApprovalRequest)
        .filter(ApprovalRequest.status == "pending", ApprovalRequest.expires_at < now_naive)
        .all()
    )
    for r in stale:
        r.status = "expired"
    db.commit()
    return len(stale)
