from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from governance.db import get_db
from governance.models import AuditEvent
from governance.audit.store import verify_chain, log_event

router = APIRouter(prefix="/audit", tags=["audit"])


class LogRequest(BaseModel):
    actor_id: str
    actor_type: str = "service"
    action: str
    resource: str
    decision: str = "recorded"
    reason: str = ""
    correlation_id: str = ""
    context_hash: str = ""


@router.post("/log")
def log(req: LogRequest, db: Session = Depends(get_db)):
    """
    Lets other services (Context Builder, and everything after it) write
    into the SAME hash-chained trail Security Layer's own decisions go
    into, rather than each module keeping a disconnected local log.
    Every module's safety-relevant events end up in one place.
    """
    event = log_event(
        db,
        actor_id=req.actor_id,
        actor_type=req.actor_type,
        action=req.action,
        resource=req.resource,
        decision=req.decision,
        reason=req.reason,
        correlation_id=req.correlation_id,
        context_hash=req.context_hash,
    )
    return {"id": event.id, "logged": True}


@router.get("/query")
def query(actor_id: Optional[str] = None, action: Optional[str] = None, correlation_id: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Phase 18: correlation_id is a real gap-fill — the standard way this
    system already threads a single task's related events together
    (every audit_log() caller since Phase 1 has passed one), but this
    query endpoint only ever supported actor_id/action filters until
    Security Agent's security.audit_query needed to pull a real, complete
    trail for one specific task rather than filtering by who or what.
    """
    q = db.query(AuditEvent)
    if actor_id:
        q = q.filter(AuditEvent.actor_id == actor_id)
    if action:
        q = q.filter(AuditEvent.action == action)
    if correlation_id:
        q = q.filter(AuditEvent.correlation_id == correlation_id)
    rows = q.order_by(AuditEvent.ts.desc()).limit(200).all()
    return [
        {
            "id": e.id,
            "ts": e.ts.isoformat(),
            "actor_id": e.actor_id,
            "actor_type": e.actor_type,
            "action": e.action,
            "resource": e.resource,
            "decision": e.decision,
            "reason": e.reason,
            "correlation_id": e.correlation_id,
        }
        for e in rows
    ]


@router.get("/verify")
def verify(db: Session = Depends(get_db)):
    """Recomputes the hash chain end to end — the check a restore drill (Phase 20) should run."""
    return verify_chain(db)
