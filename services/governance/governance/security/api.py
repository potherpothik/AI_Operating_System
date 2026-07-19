from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from governance.db import get_db
from governance.security.policy_engine import PolicyEngine
from governance.security.classifier import classify_content
from governance.audit.store import log_event

router = APIRouter(prefix="/security", tags=["security"])
_engine = PolicyEngine()


class AuthorizeRequest(BaseModel):
    actor: str
    actor_type: str = "agent"
    action: str
    resource: str
    correlation_id: str = ""


class ClassifyRequest(BaseModel):
    content: str
    declared_classification: str = "internal"


@router.post("/authorize")
def authorize(req: AuthorizeRequest, db: Session = Depends(get_db)):
    try:
        result = _engine.authorize(role=req.actor, action=req.action, resource=req.resource)
    except Exception as e:  # noqa: BLE001 — deliberately broad: fail closed on ANY error, never fail open
        result = {"decision": "deny", "reason": f"policy engine error, failing closed: {e}"}

    # Every decision is logged synchronously, before the caller gets the response —
    # an unlogged authorization is equivalent to no authorization (Phase 1).
    log_event(
        db,
        actor_id=req.actor,
        actor_type=req.actor_type,
        action=req.action,
        resource=req.resource,
        decision=result["decision"],
        reason=result["reason"],
        correlation_id=req.correlation_id,
    )
    return result


@router.post("/classify")
def classify(req: ClassifyRequest):
    """
    Heuristic content classification — a floor, not a ceiling. Returns
    the more restrictive of the caller's declared classification and
    whatever the heuristic detects, never the less restrictive one.
    """
    return classify_content(req.content, req.declared_classification)


@router.get("/policy/{role}")
def policy_for_role(role: str):
    return {"role": role, "rules": _engine.policy_for_role(role)}


@router.post("/reload")
def reload_policy():
    """Hot-reload policy files without restarting the service."""
    _engine._load()
    return {"reloaded": True, "rule_count": len(_engine.rules)}
