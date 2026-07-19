from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from extensibility.db import get_db
from extensibility import clients
from extensibility.mcp_client import store, adapter

router = APIRouter(prefix="/mcp", tags=["mcp"])


def _server_out(server) -> dict:
    return {
        "id": server.id, "name": server.name, "url": server.url, "description": server.description,
        "local_only": server.local_only, "tool_schemas": server.tool_schemas, "status": server.status,
        "registered_by": server.registered_by, "approval_id": server.approval_id,
        "registered_at": server.registered_at.isoformat(),
        "decided_at": server.decided_at.isoformat() if server.decided_at else None,
    }


class RegisterRequest(BaseModel):
    name: str
    url: str
    description: str = ""
    local_only: bool = True
    tool_schemas: Optional[dict] = None
    registered_by: str = "human_admin"


@router.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """
    Every registration is approval-gated regardless of who's asking —
    "registering one is approval-gated, mirroring capability
    registration" (doc) — not conditioned on an authorize() decision
    first, the same unconditional posture Documentation Engine's
    classify-override already established (Phase 9).
    """
    if store.get_server_by_name(db, req.name):
        raise HTTPException(status_code=409, detail=f"a server named {req.name!r} is already registered")

    risk = "medium" if req.local_only else "high"  # a remote server is the more suspicious default (doc, MCP Client Security)
    approval = clients.request_approval(
        action="mcp.register", requested_by=req.registered_by, risk_tier=risk,
        payload_ref=f"{req.name} ({req.url}) local_only={req.local_only}: {req.description}",
    )
    server = store.create_server(db, req.name, req.url, req.description, req.local_only, req.tool_schemas or {}, req.registered_by, approval.get("id"))
    clients.audit_log(
        req.registered_by, "mcp.register", req.name, decision="pending_approval",
        reason=f"url={req.url}, local_only={req.local_only}, approval_id={approval.get('id')}",
    )
    return {"server_id": server.id, "status": "pending_approval", "approval_id": approval.get("id")}


@router.post("/servers/{server_id}/activate")
def activate(server_id: str, db: Session = Depends(get_db)):
    """
    Not in the doc's own three-endpoint API table — a real, necessary
    gap: something has to turn a governance approval into this server
    actually being invocable, the same class of gap Phase 9's
    classify-override/confirm and Phase 11's raw-source-request/fetch
    both needed filled.
    """
    server = store.get_server(db, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="server not found")

    approval = clients.get_approval_status(server.approval_id)
    status = approval.get("status")
    if status == "approved":
        server = store.activate_server(db, server)
        clients.audit_log(server.registered_by, "mcp.register", server.name, decision="active")
    elif status in ("rejected", "expired"):
        server = store.reject_server(db, server)
        clients.audit_log(server.registered_by, "mcp.register", server.name, decision="rejected")
    return _server_out(server)


@router.get("/servers")
def list_servers(db: Session = Depends(get_db)):
    return {"servers": [_server_out(s) for s in store.list_servers(db)]}


class InvokeRequest(BaseModel):
    server_id: str
    tool_name: str
    params: dict = {}
    capability: str
    task_id: Optional[str] = None
    correlation_id: str = ""


@router.post("/invoke")
def invoke(req: InvokeRequest, db: Session = Depends(get_db)):
    server = store.get_server(db, req.server_id)
    if not server:
        raise HTTPException(status_code=404, detail="server not found")
    if server.status != "active":
        store.record_invocation(db, server.id, req.tool_name, req.params, None, "denied", f"server status is {server.status!r}, not active", req.capability, req.task_id, req.correlation_id)
        raise HTTPException(status_code=403, detail=f"server {server.name!r} is {server.status!r}, not active")

    decision = clients.authorize(req.capability, "mcp.invoke", server.name, correlation_id=req.correlation_id)
    if decision["decision"] == "deny":
        store.record_invocation(db, server.id, req.tool_name, req.params, None, "denied", decision.get("reason", ""), req.capability, req.task_id, req.correlation_id)
        clients.audit_log(req.capability, "mcp.invoke", server.name, decision="deny", reason=decision.get("reason", ""), correlation_id=req.correlation_id)
        raise HTTPException(status_code=403, detail=decision.get("reason", "denied by security layer"))

    expected_schema = (server.tool_schemas or {}).get(req.tool_name)
    try:
        result = adapter.invoke(server.url, req.tool_name, req.params, expected_schema=expected_schema)
    except adapter.ServerUnreachable as e:
        store.record_invocation(db, server.id, req.tool_name, req.params, None, "failed", str(e), req.capability, req.task_id, req.correlation_id)
        clients.audit_log(req.capability, "mcp.invoke", server.name, decision="failed", reason=str(e), correlation_id=req.correlation_id)
        raise HTTPException(status_code=502, detail=str(e))
    except adapter.SchemaViolation as e:
        store.record_invocation(db, server.id, req.tool_name, req.params, None, "failed", str(e), req.capability, req.task_id, req.correlation_id)
        clients.audit_log(req.capability, "mcp.invoke", server.name, decision="failed", reason=f"schema violation: {e}", correlation_id=req.correlation_id)
        raise HTTPException(status_code=502, detail=f"result violated declared schema: {e}")

    store.record_invocation(db, server.id, req.tool_name, req.params, result, "completed", "", req.capability, req.task_id, req.correlation_id)
    clients.audit_log(req.capability, "mcp.invoke", server.name, decision="completed", reason=req.tool_name, correlation_id=req.correlation_id)
    # Tagged untrusted/retrieved the same way Vector Search results are
    # (Phase 3/4's taint-tracking) — a caller folding this into a prompt
    # is responsible for wrapping it in <untrusted_context>, same as any
    # other retrieved content.
    return {"result": result, "untrusted": True, "source": f"mcp:{server.name}:{req.tool_name}"}
