import os
import httpx

SECURITY_LAYER_URL = os.environ.get("SECURITY_LAYER_URL", "http://localhost:8000")


def authorize(actor: str, action: str, resource: str, correlation_id: str = "", actor_type: str = "agent") -> dict:
    """
    Calls the real Security Layer service (Phase 1) over HTTP — these are
    genuinely separate deployable services (Phase 19), not the same process.

    Fails closed: any network error, timeout, or non-2xx response is
    treated as deny. Gateway must never treat "Security Layer unreachable"
    as "allow by default" — that would defeat the entire point of Phase 1.
    """
    try:
        resp = httpx.post(
            f"{SECURITY_LAYER_URL}/security/authorize",
            json={
                "actor": actor,
                "actor_type": actor_type,
                "action": action,
                "resource": resource,
                "correlation_id": correlation_id,
            },
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
