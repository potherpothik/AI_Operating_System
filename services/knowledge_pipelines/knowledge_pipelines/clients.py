import os
import httpx

SECURITY_LAYER_URL = os.environ.get("SECURITY_LAYER_URL", "http://localhost:8000")
KNOWLEDGE_URL = os.environ.get("KNOWLEDGE_URL", "http://localhost:8003")
DATABASE_CONNECTOR_URL = os.environ.get("DATABASE_CONNECTOR_URL", "http://localhost:8007")
ASSEMBLY_URL = os.environ.get("ASSEMBLY_URL", "http://localhost:8004")


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


def vector_ingest(source: str, content: str, project_id: str, doc_type: str, classification: str, version: str = "1") -> dict:
    resp = httpx.post(
        f"{KNOWLEDGE_URL}/vector/ingest",
        json={"source": source, "content": content, "project_id": project_id, "doc_type": doc_type, "classification": classification, "version": version},
        timeout=20.0,
    )
    resp.raise_for_status()
    return resp.json()


def vector_reindex(document_id: str, content: str) -> dict:
    resp = httpx.post(f"{KNOWLEDGE_URL}/vector/reindex/{document_id}", json={"content": content}, timeout=20.0)
    resp.raise_for_status()
    return resp.json()


def vector_delete(document_id: str) -> bool:
    resp = httpx.delete(f"{KNOWLEDGE_URL}/vector/{document_id}", timeout=20.0)
    return resp.status_code == 200


def vector_query(text: str, namespace: str = None, classification_ceiling: str = "confidential", doc_type: str = None, top_k: int = 5) -> list:
    resp = httpx.post(
        f"{KNOWLEDGE_URL}/vector/query",
        json={"text": text, "namespace": namespace, "classification_ceiling": classification_ceiling, "doc_type": doc_type, "top_k": top_k},
        timeout=20.0,
    )
    resp.raise_for_status()
    return resp.json().get("hits", [])


def memory_write(memory_type: str, namespace: str, key: str, value: str, actor: str, classification_hint: str = "internal") -> dict:
    resp = httpx.post(
        f"{KNOWLEDGE_URL}/memory/{memory_type}/write",
        json={"namespace": namespace, "key": key, "value": value, "actor": actor, "classification_hint": classification_hint},
        timeout=20.0,
    )
    resp.raise_for_status()
    return resp.json()


def model_ceiling(target_model: str) -> dict:
    """
    Phase 11: raw_source_gate.py's re-verification that target_model is
    local-only before releasing confidential raw source — reuses Context
    Builder's own model-isolation check (Phase 4) over HTTP rather than
    duplicating it. Fails toward the most restrictive tier ("public",
    i.e. not local) if Context Builder is unreachable — never "assume
    local and release it."
    """
    try:
        resp = httpx.get(f"{ASSEMBLY_URL}/context/model-ceiling", params={"target_model": target_model}, timeout=10.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:  # noqa: BLE001
        return {"ceiling": "public", "reason": f"context builder unreachable, failing closed: {e}"}


class SchemaFetchFailed(Exception):
    pass


def fetch_schema(target_db: str, capability: str) -> dict:
    """
    Raises rather than returning a fallback — a failed live sync must mark
    affected knowledge stale, never silently keep serving whatever was
    synced last time as if it were current (Phase 9 doc, ERP Knowledge
    Engine failure handling, inherited from Phase 7's own fail-closed
    schema-read discipline).
    """
    try:
        resp = httpx.get(f"{DATABASE_CONNECTOR_URL}/db/schema/{target_db}", params={"capability": capability}, timeout=20.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:  # noqa: BLE001
        raise SchemaFetchFailed(str(e))
