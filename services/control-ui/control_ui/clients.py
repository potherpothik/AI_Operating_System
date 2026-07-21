import os
import httpx

SECURITY_LAYER_URL = os.environ.get("SECURITY_LAYER_URL", "http://localhost:8000")
PLATFORM_URL = os.environ.get("PLATFORM_URL", "http://localhost:8002")
OBSERVABILITY_URL = os.environ.get("OBSERVABILITY_URL", "http://localhost:8013")


def authorize(actor: str, action: str, resource: str, correlation_id: str = "") -> dict:
    """Same fail-closed pattern every other service's own client uses
    (platform-spine, extensibility) — the BFF makes no allow/deny
    decision of its own, same posture as Gateway."""
    try:
        resp = httpx.post(
            f"{SECURITY_LAYER_URL}/security/authorize",
            json={"actor": actor, "actor_type": "human", "action": action, "resource": resource, "correlation_id": correlation_id},
            timeout=5.0,
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
                "actor_id": actor_id, "actor_type": "human", "action": action, "resource": resource,
                "decision": decision, "reason": reason, "correlation_id": correlation_id,
            },
            timeout=5.0,
        )
        return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def is_reachable(url: str) -> bool:
    try:
        return httpx.get(f"{url}/", timeout=2.0).status_code == 200
    except Exception:
        return False


def forward_approval_decision(approval_id: str, decided_by: str, approve: bool, comment: str = "") -> dict:
    resp = httpx.post(
        f"{SECURITY_LAYER_URL}/approval/{approval_id}/decide",
        json={"decided_by": decided_by, "approve": approve, "comment": comment},
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()


def list_pending_approvals() -> list:
    resp = httpx.get(f"{SECURITY_LAYER_URL}/approval/pending", timeout=10.0)
    resp.raise_for_status()
    return resp.json()


def get_conversation(conversation_id: str, token: str) -> dict | None:
    resp = httpx.get(
        f"{PLATFORM_URL}/api/v1/conversations/{conversation_id}",
        headers={"Authorization": f"Bearer {token}"}, timeout=10.0,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def list_conversations(token: str) -> list:
    resp = httpx.get(f"{PLATFORM_URL}/api/v1/conversations", headers={"Authorization": f"Bearer {token}"}, timeout=10.0)
    resp.raise_for_status()
    return resp.json()


def create_conversation(title: str, token: str) -> dict:
    resp = httpx.post(
        f"{PLATFORM_URL}/api/v1/conversations", json={"title": title},
        headers={"Authorization": f"Bearer {token}"}, timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()


def list_tasks_for_conversation(conversation_id: str, token: str) -> list:
    resp = httpx.get(
        f"{PLATFORM_URL}/api/v1/tasks", params={"conversation_id": conversation_id},
        headers={"Authorization": f"Bearer {token}"}, timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()


def get_task_events(task_id: str, token: str) -> list:
    resp = httpx.get(f"{PLATFORM_URL}/api/v1/tasks/{task_id}/events", headers={"Authorization": f"Bearer {token}"}, timeout=10.0)
    resp.raise_for_status()
    return resp.json()
