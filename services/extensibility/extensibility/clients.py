import os
import httpx

SECURITY_LAYER_URL = os.environ.get("SECURITY_LAYER_URL", "http://localhost:8000")
ASSEMBLY_URL = os.environ.get("ASSEMBLY_URL", "http://localhost:8004")
AGENTS_URL = os.environ.get("AGENTS_URL", "http://localhost:8005")


def authorize(actor: str, action: str, resource: str, correlation_id: str = "") -> dict:
    try:
        resp = httpx.post(
            f"{SECURITY_LAYER_URL}/security/authorize",
            json={"actor": actor, "actor_type": "service", "action": action, "resource": resource, "correlation_id": correlation_id},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:  # noqa: BLE001 — fail closed
        return {"decision": "deny", "reason": f"security layer unreachable, failing closed: {e}"}


def audit_log(actor_id: str, action: str, resource: str, decision: str = "recorded", reason: str = "", correlation_id: str = "") -> bool:
    try:
        resp = httpx.post(
            f"{SECURITY_LAYER_URL}/audit/log",
            json={
                "actor_id": actor_id, "actor_type": "service", "action": action, "resource": resource,
                "decision": decision, "reason": reason, "correlation_id": correlation_id,
            },
            timeout=10.0,
        )
        return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def request_approval(action: str, requested_by: str, risk_tier: str = "medium", payload_ref: str = "") -> dict:
    try:
        resp = httpx.post(
            f"{SECURITY_LAYER_URL}/approval/request",
            json={"action": action, "requested_by": requested_by, "risk_tier": risk_tier, "payload_ref": payload_ref},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:  # noqa: BLE001
        return {"id": None, "status": "rejected", "reason": f"approval layer unreachable, failing closed: {e}"}


def get_approval_status(approval_id: str) -> dict:
    try:
        resp = httpx.get(f"{SECURITY_LAYER_URL}/approval/{approval_id}", timeout=10.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:  # noqa: BLE001
        return {"status": "unknown", "reason": str(e)}


def register_template(agent_template_id: str, body: str, expected_output_schema: dict, created_by: str) -> dict:
    """Same registration path every agent's own register.py uses (Phase 5)
    — Plugin System is just another caller of Prompt Builder's existing,
    already-approval-gated template registration, not a second mechanism."""
    resp = httpx.post(
        f"{ASSEMBLY_URL}/prompt/templates",
        json={"agent_template_id": agent_template_id, "body": body, "expected_output_schema": expected_output_schema, "created_by": created_by},
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()


def reload_agent_capabilities() -> dict:
    """
    Best-effort — a plugin's capability.yaml is written to disk regardless
    (store.py), so it's picked up on the agents service's own next
    restart even if this call fails; this just avoids requiring one for
    the common case.
    """
    try:
        resp = httpx.post(f"{AGENTS_URL}/capabilities/reload", timeout=10.0)
        resp.raise_for_status()
        return {"attempted": True, "result": resp.json()}
    except Exception as e:  # noqa: BLE001
        return {"attempted": True, "failed": True, "reason": str(e)}
