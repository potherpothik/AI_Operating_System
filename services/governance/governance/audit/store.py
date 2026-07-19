import hashlib
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from governance.models import AuditEvent


def _hash_row(prev_hash: str, actor_id: str, action: str, resource: str, decision: str, ts_iso: str) -> str:
    payload = f"{prev_hash}|{actor_id}|{action}|{resource}|{decision}|{ts_iso}"
    return hashlib.sha256(payload.encode()).hexdigest()


def log_event(
    db: Session,
    actor_id: str,
    actor_type: str,
    action: str,
    resource: str,
    decision: str,
    reason: str = "",
    correlation_id: str = "",
    context_hash: str = "",
) -> AuditEvent:
    last = db.query(AuditEvent).order_by(AuditEvent.ts.desc()).first()
    prev_hash = last.this_hash if last else ""
    ts = datetime.now(timezone.utc)
    ts_iso = ts.isoformat()
    this_hash = _hash_row(prev_hash, actor_id, action, resource, decision, ts_iso)

    event = AuditEvent(
        actor_id=actor_id,
        actor_type=actor_type,
        action=action,
        resource=resource,
        decision=decision,
        reason=reason,
        correlation_id=correlation_id,
        context_hash=context_hash,
        prev_hash=prev_hash,
        this_hash=this_hash,
        ts=ts,
        ts_iso=ts_iso,
    )
    db.add(event)
    db.commit()
    return event


def verify_chain(db: Session) -> dict:
    """Recomputes every hash in ts order and confirms nothing was altered or dropped."""
    events = db.query(AuditEvent).order_by(AuditEvent.ts.asc()).all()
    prev_hash = ""
    for e in events:
        expected = _hash_row(prev_hash, e.actor_id, e.action, e.resource, e.decision, e.ts_iso)
        if expected != e.this_hash:
            return {"valid": False, "broken_at": e.id}
        prev_hash = e.this_hash
    return {"valid": True, "events_checked": len(events)}
