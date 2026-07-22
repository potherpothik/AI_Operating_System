import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from control_ui import clients, bootstrap, timeline
from control_ui.auth import resolve_actor, resolve_bearer_token, resolve_raw_token_if_oidc

router = APIRouter(prefix="/ui", tags=["control-ui"])


@router.get("/healthz")
def healthz():
    return {"status": "ok", "phase": 24}


@router.get("/bootstrap")
def get_bootstrap(actor: str = Depends(resolve_actor)):
    return bootstrap.build(actor)


class ConversationCreate(BaseModel):
    title: str = "New conversation"


@router.get("/conversations")
def list_conversations(token: str = Depends(resolve_bearer_token)):
    return clients.list_conversations(token)


@router.post("/conversations")
def create_conversation(body: ConversationCreate, token: str = Depends(resolve_bearer_token)):
    return clients.create_conversation(body.title, token)


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, token: str = Depends(resolve_bearer_token)):
    conversation = clients.get_conversation(conversation_id, token)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation not found")
    return conversation


@router.get("/conversations/{conversation_id}/timeline")
def get_timeline(conversation_id: str, token: str = Depends(resolve_bearer_token)):
    conversation = clients.get_conversation(conversation_id, token)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation not found")
    return timeline.build(conversation_id, token)


@router.get("/approvals/inbox")
def approvals_inbox(actor: str = Depends(resolve_actor)):
    """
    Real fields only — id, action, requested_by, risk_tier, created_at,
    expires_at. NOT enriched with task/conversation links: ApprovalRequest
    (governance/models.py) has no correlation_id or task_id field today,
    so there is nothing real to join against. Named honestly here rather
    than fabricated — see services/control-ui/README.md.
    """
    return clients.list_pending_approvals()


class ApprovalDecide(BaseModel):
    approve: bool
    comment: str = ""


@router.post("/approvals/{approval_id}/decide")
def decide_approval(approval_id: str, body: ApprovalDecide, actor: str = Depends(resolve_actor), raw_token: str = Depends(resolve_raw_token_if_oidc)):
    correlation_id = str(uuid.uuid4())
    decision = clients.authorize(actor=actor, action="approval.decide", resource=approval_id, correlation_id=correlation_id, token=raw_token)
    if decision["decision"] == "deny":
        clients.audit_log(
            actor_id=actor, action="approval.decide", resource=approval_id,
            decision="deny", reason=decision.get("reason", ""), correlation_id=correlation_id,
        )
        raise HTTPException(status_code=403, detail=decision.get("reason", "denied by security layer"))

    result = clients.forward_approval_decision(approval_id, decided_by=actor, approve=body.approve, comment=body.comment)
    clients.audit_log(
        actor_id=actor, action="approval.decide", resource=approval_id,
        decision=result.get("status", "unknown"), correlation_id=correlation_id,
    )
    return result


@router.get("/views")
def list_views():
    """
    Honestly empty (Phase 24 doc §5.5's own "v1 honesty" note) —
    extensibility has no view-manifest convention today (§1 gap-fill row,
    not built this session). An empty catalog is a valid, real answer,
    not a placeholder for a broken feature.
    """
    return {"views": []}
