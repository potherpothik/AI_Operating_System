import os
import httpx

SECURITY_LAYER_URL = os.environ.get("SECURITY_LAYER_URL", "http://localhost:8000")


def authorize(actor: str, action: str, resource: str, correlation_id: str = "", actor_type: str = "agent", token: str = None) -> dict:
    """
    Calls the real Security Layer service (Phase 1) over HTTP — these are
    genuinely separate deployable services (Phase 19), not the same process.

    Fails closed: any network error, timeout, or non-2xx response is
    treated as deny. Gateway must never treat "Security Layer unreachable"
    as "allow by default" — that would defeat the entire point of Phase 1.

    Phase 31: `token`, when passed (AUTH_MODE=oidc), is a real OIDC
    bearer token — governance verifies it itself and authorizes by its
    real `role` claim rather than trusting `actor` as a role name
    unverified. `actor` is still sent for the AUTH_MODE=stub path,
    unchanged.
    """
    try:
        body = {
            "actor": actor,
            "actor_type": actor_type,
            "action": action,
            "resource": resource,
            "correlation_id": correlation_id,
        }
        if token:
            body["token"] = token
        resp = httpx.post(
            f"{SECURITY_LAYER_URL}/security/authorize",
            json=body,
            timeout=5.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:  # noqa: BLE001 — deliberately broad: fail closed on ANY error
        return {"decision": "deny", "reason": f"security layer unreachable, failing closed: {e}"}


def is_security_layer_reachable() -> bool:
    try:
        resp = httpx.get(f"{SECURITY_LAYER_URL}/", timeout=2.0)
        return resp.status_code == 200
    except Exception:
        return False


def classify(content: str, declared_classification: str = "internal") -> dict:
    """
    Phase 27: real call to Security Layer's classify heuristic (Phase 1)
    — the same fail-conservative posture as authorize(). Unreachable
    Security Layer means the OpenAI shim must not guess a classification
    on its own behalf; the caller treats an exception here as "assume
    confidential," never "assume public."
    """
    resp = httpx.post(
        f"{SECURITY_LAYER_URL}/security/classify",
        json={"content": content, "declared_classification": declared_classification},
        timeout=5.0,
    )
    resp.raise_for_status()
    return resp.json()


def audit_log(actor_id: str, action: str, resource: str, decision: str, reason: str = "", correlation_id: str = "") -> None:
    """Phase 27: direct write to the shared, hash-chained audit trail —
    same endpoint every other service's own bridge already writes
    through (e.g. services/agents/agents/reasoning_engine/mcp_bridge.py)."""
    try:
        httpx.post(
            f"{SECURITY_LAYER_URL}/audit/log",
            json={
                "actor_id": actor_id, "actor_type": "agent", "action": action, "resource": resource,
                "decision": decision, "reason": reason, "correlation_id": correlation_id,
            },
            timeout=5.0,
        )
    except Exception:  # noqa: BLE001 — best-effort, never blocks the real response on a logging failure
        pass
