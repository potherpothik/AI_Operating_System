from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from planning.db import get_db
from planning import clients
from planning.capability_registry import store, loader

router = APIRouter(prefix="/capabilities", tags=["capabilities"])


def _entry_out(entry) -> dict:
    return {
        "id": entry.id,
        "agent_capability": entry.agent_capability,
        "version": entry.version,
        "allowed_actions": entry.allowed_actions,
        "forbidden_actions": entry.forbidden_actions,
        "requires_approval": entry.requires_approval,
        "classification_ceiling": entry.classification_ceiling,
        "status": entry.status,
        "registered_at": entry.registered_at.isoformat(),
        "deprecated_at": entry.deprecated_at.isoformat() if entry.deprecated_at else None,
    }


@router.get("")
def list_capabilities(action_type: str = None, classification_ceiling: str = None, status: str = "active", db: Session = Depends(get_db)):
    rows = store.list_all(db, action_type=action_type, classification_ceiling=classification_ceiling, status=status)
    return {"capabilities": [_entry_out(r) for r in rows]}


@router.get("/{entry_id}")
def get_capability(entry_id: str, db: Session = Depends(get_db)):
    entry = store.get(db, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="capability entry not found")
    return _entry_out(entry)


class RegisterRequest(BaseModel):
    agent_capability: str
    allowed_actions: list[str]
    forbidden_actions: list[str] = []
    requires_approval: list[str] = []
    classification_ceiling: str = "internal"
    requested_by: str = "planner"


@router.post("/register")
def register_capability(req: RegisterRequest, db: Session = Depends(get_db)):
    """
    Explicit registration path (distinct from the automatic /capabilities/
    sync below) — same new-vs-scope-change distinction: a genuinely new
    agent_capability activates immediately, a change to an existing one's
    scope requires real governance approval first.
    """
    active = store.get_active(db, req.agent_capability)

    if not active:
        decision = clients.authorize(req.requested_by, "capability.register_new", req.agent_capability)
        if decision["decision"] != "allow":
            raise HTTPException(status_code=403, detail=decision.get("reason", "denied"))
        entry = store.create_active(db, req.agent_capability, req.allowed_actions, req.forbidden_actions, req.requires_approval, req.classification_ceiling, version="1")
        clients.audit_log(req.requested_by, "capability.register_new", req.agent_capability, decision="allow")
        return _entry_out(entry)

    if store.scope_matches(active, req.allowed_actions, req.forbidden_actions, req.requires_approval, req.classification_ceiling):
        return _entry_out(active)

    next_version = str(int(active.version) + 1) if active.version.isdigit() else "2"
    approval = clients.request_approval(action=f"capability.change_scope.{req.agent_capability}", requested_by=req.requested_by, risk_tier="medium", payload_ref=req.agent_capability)
    entry = store.create_pending(db, req.agent_capability, req.allowed_actions, req.forbidden_actions, req.requires_approval, req.classification_ceiling, next_version, approval.get("id"))
    return _entry_out(entry)


class DeprecateRequest(BaseModel):
    requested_by: str = "planner"


@router.post("/{entry_id}/deprecate")
def deprecate_capability(entry_id: str, req: DeprecateRequest, db: Session = Depends(get_db)):
    entry = store.get(db, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="capability entry not found")

    decision = clients.authorize(req.requested_by, "capability.deprecate", entry.agent_capability)
    if decision["decision"] == "deny":
        raise HTTPException(status_code=403, detail=decision.get("reason", "denied"))
    if decision["decision"] == "require_approval":
        approval = clients.request_approval(action=f"capability.deprecate.{entry.agent_capability}", requested_by=req.requested_by, risk_tier="medium", payload_ref=entry.agent_capability)
        entry.approval_id = approval.get("id")
        db.commit()
        return {"status": "pending_approval", "approval_id": approval.get("id")}

    finalized = store.finalize_deprecation(db, entry_id)
    return _entry_out(finalized)


@router.post("/{entry_id}/deprecate/confirm")
def confirm_deprecation(entry_id: str, db: Session = Depends(get_db)):
    """Called once the deprecation's approval has resolved — mirrors the
    reconcile pattern used elsewhere rather than deprecating optimistically."""
    entry = store.get(db, entry_id)
    if not entry or not entry.approval_id:
        raise HTTPException(status_code=404, detail="no pending deprecation for this entry")
    result = clients.get_approval_status(entry.approval_id)
    if result.get("status") != "approved":
        return {"status": result.get("status", "unknown")}
    finalized = store.finalize_deprecation(db, entry_id)
    return _entry_out(finalized)


@router.post("/sync")
def sync(db: Session = Depends(get_db)):
    try:
        results = loader.sync_from_agents(db)
    except Exception as e:  # noqa: BLE001 — fail closed: never silently proceed with a partial/stale roster
        raise HTTPException(status_code=502, detail=f"agents service unreachable, sync aborted: {e}")
    return results


@router.post("/reconcile-approvals")
def reconcile(db: Session = Depends(get_db)):
    updated = loader.reconcile_pending(db)
    return {"updated": updated}
