from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from governance.db import get_db
from governance.models import ApprovalRequest
from governance.approval import store
from governance.audit.store import log_event

router = APIRouter(prefix="/approval", tags=["approval"])


class ApprovalCreate(BaseModel):
    action: str
    requested_by: str
    risk_tier: str = "medium"
    payload_ref: str = ""


class ApprovalDecision(BaseModel):
    decided_by: str
    approve: bool
    comment: str = ""


@router.post("/request")
def request_approval(req: ApprovalCreate, db: Session = Depends(get_db)):
    r = store.create_request(db, req.action, req.requested_by, req.risk_tier, req.payload_ref)
    log_event(
        db,
        actor_id=req.requested_by,
        actor_type="agent",
        action=req.action,
        resource=r.id,
        decision="pending_approval",
    )
    return {"id": r.id, "status": r.status, "expires_at": r.expires_at.isoformat()}


@router.get("/pending")
def pending(db: Session = Depends(get_db)):
    store.expire_stale(db)  # lazily expire anything past its TTL before listing
    rows = db.query(ApprovalRequest).filter(ApprovalRequest.status == "pending").all()
    return [
        {
            "id": r.id,
            "action": r.action,
            "requested_by": r.requested_by,
            "risk_tier": r.risk_tier,
            "created_at": r.created_at.isoformat(),
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
        }
        for r in rows
    ]


@router.get("")
def list_approvals(status: str = None, db: Session = Depends(get_db)):
    """
    Phase 13: the general listing `/pending` never was — Metrics
    Dashboard needs decided (approved/rejected/expired) requests too, to
    compute time-to-decision (`decided_at - created_at`), not just the
    still-open queue. Same lazy-expire-before-listing behavior as
    `/pending` so a stale-past-TTL row never shows as `status=pending`
    here either.
    """
    store.expire_stale(db)
    query = db.query(ApprovalRequest)
    if status:
        query = query.filter(ApprovalRequest.status == status)
    rows = query.order_by(ApprovalRequest.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "action": r.action,
            "status": r.status,
            "requested_by": r.requested_by,
            "risk_tier": r.risk_tier,
            "created_at": r.created_at.isoformat(),
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            "decided_by": r.decided_by,
            "decided_at": r.decided_at.isoformat() if r.decided_at else None,
        }
        for r in rows
    ]


@router.get("/{request_id}")
def get_request(request_id: str, db: Session = Depends(get_db)):
    store.expire_stale(db)
    r = db.query(ApprovalRequest).filter(ApprovalRequest.id == request_id).first()
    if not r:
        return {"error": "not found"}
    return {
        "id": r.id,
        "action": r.action,
        "status": r.status,
        "requested_by": r.requested_by,
        "risk_tier": r.risk_tier,
        "decided_by": r.decided_by,
        "decided_at": r.decided_at.isoformat() if r.decided_at else None,
        "comment": r.comment,
    }


@router.post("/{request_id}/decide")
def decide(request_id: str, body: ApprovalDecision, db: Session = Depends(get_db)):
    r = store.decide(db, request_id, body.decided_by, body.approve, body.comment)
    if not r:
        return {"error": "not found"}
    log_event(
        db,
        actor_id=body.decided_by,
        actor_type="human",
        action="approval_decision",
        resource=request_id,
        decision=r.status,
    )
    return {"id": r.id, "status": r.status}
