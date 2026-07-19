import os
import httpx

SECURITY_LAYER_URL = os.environ.get("SECURITY_LAYER_URL", "http://localhost:8000")
AGENTS_URL = os.environ.get("AGENTS_URL", "http://localhost:8005")
PLATFORM_URL = os.environ.get("PLATFORM_URL", "http://localhost:8002")
GATEWAY_TOKEN = os.environ.get("GATEWAY_TOKEN", "dev-planner-token")


def authorize(actor: str, action: str, resource: str, correlation_id: str = "") -> dict:
    try:
        resp = httpx.post(
            f"{SECURITY_LAYER_URL}/security/authorize",
            json={"actor": actor, "actor_type": "agent", "action": action, "resource": resource, "correlation_id": correlation_id},
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


class AgentsUnreachable(Exception):
    pass


def fetch_agent_capabilities() -> list:
    """
    The one and only source Capability Registry syncs from — the agents
    service's own introspection endpoint, which reflects what Reasoning
    Engine actually has loaded and enforces (not a copy that could drift).
    Raises rather than returning an empty list on failure — an empty
    roster looks identical to "no agents exist yet", which would
    incorrectly deprecate every real capability on the next sync.
    """
    resp = httpx.get(f"{AGENTS_URL}/capabilities", timeout=10.0)
    resp.raise_for_status()
    return resp.json()["capabilities"]


def execute_reasoning(task_id: str, task_description: str, agent_capability: str, namespace: str = "default",
                       target_model: str = None, correlation_id: str = None) -> dict:
    # Omit unset optional fields entirely rather than sending an explicit
    # `null` — found live: Pydantic v2's "field: str = None" only sets a
    # default, it does not widen the type to accept a real `null` in the
    # request body, so an explicit null 422s even though the field is
    # meant to be optional. Omitting the key sidesteps that regardless of
    # whether the receiving service's model happens to be written
    # correctly for this — a more robust general habit for any HTTP
    # client in this system, not just a workaround for one endpoint.
    body = {"task_id": task_id, "task_description": task_description, "agent_capability": agent_capability, "namespace": namespace}
    if target_model is not None:
        body["target_model"] = target_model
    if correlation_id is not None:
        body["correlation_id"] = correlation_id
    # Generous timeout: a full execution can involve up to max_iterations
    # (default 8) real model calls if the model struggles to produce
    # valid structured output for an ambiguous task — confirmed live,
    # this genuinely happens rather than being a hung connection.
    resp = httpx.post(f"{AGENTS_URL}/reasoning/execute", json=body, timeout=300.0)
    resp.raise_for_status()
    return resp.json()


def create_subtask(title: str, description: str, correlation_id: str = "", parent_task_id: str = None) -> dict:
    try:
        resp = httpx.post(
            f"{PLATFORM_URL}/api/v1/tasks",
            json={"title": title, "description": description, "priority": "normal", "context_refs": parent_task_id or ""},
            headers={"Authorization": f"Bearer {GATEWAY_TOKEN}"},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:  # noqa: BLE001
        return {"id": None, "error": str(e)}
