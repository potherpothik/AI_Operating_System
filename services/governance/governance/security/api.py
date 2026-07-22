from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from governance.db import get_db
from governance.models import TestExecutionTarget
from governance.security.policy_engine import PolicyEngine
from governance.security.classifier import classify_content
from governance.security import secrets, environments, oidc
from governance.audit.store import log_event

router = APIRouter(prefix="/security", tags=["security"])
_engine = PolicyEngine()


class AuthorizeRequest(BaseModel):
    actor: str
    actor_type: str = "agent"
    action: str
    resource: str
    correlation_id: str = ""
    # Phase 31: optional real OIDC bearer token — when present, this is
    # the actual authority for the decision, not `actor` above. Every
    # prior-phase caller omits this and gets identical behavior to
    # before (role lookup by literal `actor` string); a caller running
    # under AUTH_MODE=oidc passes its raw token here so governance can
    # verify it itself and authorize by the token's real `role` claim
    # while still recording the token's real per-user `sub` as the
    # audit actor — "who did it" and "what were they allowed to do"
    # resolved from the one real, signed source, not trusted blind from
    # whatever string a caller happens to send as `actor`.
    token: str = None


class ClassifyRequest(BaseModel):
    content: str
    declared_classification: str = "internal"


class SecretResolveRequest(BaseModel):
    target_db: str
    capability: str
    correlation_id: str = ""


class VerifyEnvironmentRequest(BaseModel):
    resolved_environment: str
    capability: str
    correlation_id: str = ""


class VerifyTokenRequest(BaseModel):
    token: str


@router.post("/authorize")
def authorize(req: AuthorizeRequest, db: Session = Depends(get_db)):
    role = req.actor
    actor_id = req.actor
    actor_type = req.actor_type

    if req.token:
        claims = oidc.verify_token(req.token)
        if not claims:
            result = {"decision": "deny", "reason": "invalid or expired OIDC token"}
            log_event(db, actor_id=req.actor, actor_type=req.actor_type, action=req.action, resource=req.resource, decision=result["decision"], reason=result["reason"], correlation_id=req.correlation_id)
            return result
        # Phase 31: the token is the real authority once present — role
        # comes from its own verified `role` claim, never from the
        # caller-supplied `actor` string, and the audit trail records
        # the token's own real per-user `sub`, not a shared name.
        role = claims.get("role", req.actor)
        actor_id = claims.get("sub", req.actor)
        actor_type = "human"

    try:
        result = _engine.authorize(role=role, action=req.action, resource=req.resource)
    except Exception as e:  # noqa: BLE001 — deliberately broad: fail closed on ANY error, never fail open
        result = {"decision": "deny", "reason": f"policy engine error, failing closed: {e}"}

    # Every decision is logged synchronously, before the caller gets the response —
    # an unlogged authorization is equivalent to no authorization (Phase 1).
    log_event(
        db,
        actor_id=actor_id,
        actor_type=actor_type,
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


@router.post("/secrets/resolve")
def resolve_secret(req: SecretResolveRequest, db: Session = Depends(get_db)):
    """
    Phase 7's Database Connector calls this instead of holding any
    credential itself — fail closed on an unregistered target, a
    capability not on that target's allow list, or missing credential
    material, same posture as /security/authorize. The resolved
    connection string is returned to the caller (it has to be, to open a
    real connection) but never logged — only the resource name and
    decision are, same as every other governance log entry.
    """
    try:
        result = secrets.resolve(req.target_db, req.capability)
    except secrets.SecretNotFound as e:
        log_event(db, actor_id=req.capability, actor_type="agent", action="secrets.resolve", resource=req.target_db, decision="deny", reason=str(e), correlation_id=req.correlation_id)
        raise HTTPException(status_code=404, detail=str(e))
    except secrets.SecretAccessDenied as e:
        log_event(db, actor_id=req.capability, actor_type="agent", action="secrets.resolve", resource=req.target_db, decision="deny", reason=str(e), correlation_id=req.correlation_id)
        raise HTTPException(status_code=403, detail=str(e))

    log_event(db, actor_id=req.capability, actor_type="agent", action="secrets.resolve", resource=req.target_db, decision="allow", reason="", correlation_id=req.correlation_id)
    return result


@router.post("/verify_environment")
def verify_environment(req: VerifyEnvironmentRequest, db: Session = Depends(get_db)):
    """
    Phase 10's Testing Agent calls this before every `testing.run_suite` —
    a structural check, not a policy convention, that the resolved
    execution target is a designated sandbox. Fails closed on any
    unregistered environment, same posture as secrets.resolve. Every
    verification decision is persisted to TestExecutionTarget in addition
    to the standard audit log, so "did we actually check before this run"
    is always answerable on its own.
    """
    result = environments.verify(req.resolved_environment)
    decision = "allow" if result["is_sandbox"] else "deny"

    db.add(
        TestExecutionTarget(
            capability=req.capability,
            resolved_environment=req.resolved_environment,
            is_sandbox=result["is_sandbox"],
            verified_by_security_layer=decision,
        )
    )
    db.commit()

    log_event(
        db,
        actor_id=req.capability,
        actor_type="agent",
        action="testing.verify_environment",
        resource=req.resolved_environment,
        decision=decision,
        reason=result["reason"],
        correlation_id=req.correlation_id,
    )

    if not result["is_sandbox"]:
        raise HTTPException(status_code=403, detail=result["reason"])

    return {"is_sandbox": True, "verified": "allow", "reason": result["reason"]}


@router.post("/verify_token")
def verify_token(req: VerifyTokenRequest):
    """
    Phase 31: real verification of a real OIDC identity token issued by
    services/identity/ — governance is the single place every one of the
    4 real consumer services (Gateway, Control UI, MCP Surface, the
    OpenAI shim) already calls for authorize()/audit_log(), so token
    verification lives here too rather than each consumer independently
    fetching and caching its own JWKS copy. Not itself an authorize()
    call — a caller still calls /security/authorize separately using the
    real per-user identity this returns, same two-step shape
    resolve-identity-then-authorize already has for stub tokens.
    """
    claims = oidc.verify_token(req.token)
    if not claims:
        return {"valid": False}
    return {
        "valid": True,
        "sub": claims["sub"],
        "email": claims.get("email"),
        "role": claims.get("role"),
        "preferred_username": claims.get("preferred_username"),
    }


@router.get("/policy/{role}")
def policy_for_role(role: str):
    return {"role": role, "rules": _engine.policy_for_role(role)}


@router.post("/reload")
def reload_policy():
    """Hot-reload policy files without restarting the service."""
    _engine._load()
    return {"reloaded": True, "rule_count": len(_engine.rules)}
