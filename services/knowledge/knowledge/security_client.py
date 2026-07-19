import os
import httpx

SECURITY_LAYER_URL = os.environ.get("SECURITY_LAYER_URL", "http://localhost:8000")


def authorize(actor: str, action: str, resource: str, correlation_id: str = "", actor_type: str = "agent") -> dict:
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
    except Exception as e:  # noqa: BLE001 — fail closed on ANY error
        return {"decision": "deny", "reason": f"security layer unreachable, failing closed: {e}"}


def classify(content: str, declared_classification: str = "internal") -> dict:
    """
    Fails closed toward the MOST restrictive tier if Security Layer is
    unreachable — an unclassifiable write should never default to a
    permissive tier just because the classifier couldn't be reached.
    """
    try:
        resp = httpx.post(
            f"{SECURITY_LAYER_URL}/security/classify",
            json={"content": content, "declared_classification": declared_classification},
            timeout=5.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:  # noqa: BLE001
        return {
            "classification": "confidential",
            "declared_classification": declared_classification,
            "heuristic_floor": "confidential",
            "reason": f"security layer unreachable, failing to most-restrictive tier: {e}",
        }
