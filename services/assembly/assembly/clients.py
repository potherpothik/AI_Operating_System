import os
import httpx

KNOWLEDGE_URL = os.environ.get("KNOWLEDGE_URL", "http://localhost:8003")
PLATFORM_URL = os.environ.get("PLATFORM_URL", "http://localhost:8002")
SECURITY_LAYER_URL = os.environ.get("SECURITY_LAYER_URL", "http://localhost:8000")


def memory_query(memory_type: str, namespace: str, text: str, requester_ceiling: str = "confidential", limit: int = 10) -> list:
    try:
        resp = httpx.post(
            f"{KNOWLEDGE_URL}/memory/{memory_type}/query",
            json={"namespace": namespace, "text": text, "requester_ceiling": requester_ceiling, "limit": limit},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json().get("hits", [])
    except Exception:  # noqa: BLE001 — Context Builder degrades to "partial", never crashes on this
        return []


def vector_query(text: str, namespace: str, classification_ceiling: str = "confidential", top_k: int = 5) -> list:
    try:
        resp = httpx.post(
            f"{KNOWLEDGE_URL}/vector/query",
            json={"text": text, "namespace": namespace, "classification_ceiling": classification_ceiling, "top_k": top_k},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json().get("hits", [])
    except Exception:  # noqa: BLE001
        return []


def get_reasoning_engine_config() -> dict:
    """Used to decide whether a target model counts as local or external — see classification.py."""
    try:
        resp = httpx.get(f"{PLATFORM_URL}/config/reasoning_engine", timeout=5.0)
        resp.raise_for_status()
        return resp.json()
    except Exception:  # noqa: BLE001
        # Fail toward the MOST restrictive assumption: if config is unreachable,
        # assume external models are not allowed and no local model is known —
        # never fail toward "everything is trusted local infrastructure".
        return {"external_model_allowed": False, "default_local_model": None, "fallback_local_model": None}


def audit_log(actor_id: str, action: str, resource: str, decision: str = "recorded", reason: str = "", correlation_id: str = "") -> bool:
    try:
        resp = httpx.post(
            f"{SECURITY_LAYER_URL}/audit/log",
            json={
                "actor_id": actor_id, "actor_type": "service", "action": action, "resource": resource,
                "decision": decision, "reason": reason, "correlation_id": correlation_id,
            },
            timeout=5.0,
        )
        return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def request_approval(action: str, requested_by: str, risk_tier: str = "medium", payload_ref: str = "") -> dict:
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


def get_approval_status(approval_id: str) -> dict:
    try:
        resp = httpx.get(f"{SECURITY_LAYER_URL}/approval/{approval_id}", timeout=5.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:  # noqa: BLE001
        return {"status": "unknown", "reason": str(e)}
