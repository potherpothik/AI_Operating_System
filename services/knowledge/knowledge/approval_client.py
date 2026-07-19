import os
import httpx

SECURITY_LAYER_URL = os.environ.get("SECURITY_LAYER_URL", "http://localhost:8000")


def request_approval(action: str, requested_by: str, risk_tier: str = "medium", payload_ref: str = "") -> dict:
    """
    Fails closed: if Phase 1 is unreachable, returns a synthetic rejected
    response rather than pretending a request was created — a caller must
    never treat "couldn't reach the approval layer" as "go ahead anyway".
    """
    try:
        resp = httpx.post(
            f"{SECURITY_LAYER_URL}/approval/request",
            json={"action": action, "requested_by": requested_by, "risk_tier": risk_tier, "payload_ref": payload_ref},
            timeout=5.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:  # noqa: BLE001
        return {"id": None, "status": "rejected", "reason": f"approval layer unreachable, failing closed: {e}"}


def get_status(approval_id: str) -> dict:
    try:
        resp = httpx.get(f"{SECURITY_LAYER_URL}/approval/{approval_id}", timeout=5.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:  # noqa: BLE001
        return {"status": "unknown", "reason": f"approval layer unreachable: {e}"}
