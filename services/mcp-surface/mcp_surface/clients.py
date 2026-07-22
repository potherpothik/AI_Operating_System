import os
import uuid
import httpx

SECURITY_LAYER_URL = os.environ.get("SECURITY_LAYER_URL", "http://localhost:8000")
PLATFORM_URL = os.environ.get("PLATFORM_URL", "http://localhost:8002")
AGENTS_URL = os.environ.get("AGENTS_URL", "http://localhost:8005")
KNOWLEDGE_URL = os.environ.get("KNOWLEDGE_URL", "http://localhost:8003")
KNOWLEDGE_PIPELINES_URL = os.environ.get("KNOWLEDGE_PIPELINES_URL", "http://localhost:8009")
PLANNING_URL = os.environ.get("PLANNING_URL", "http://localhost:8008")

# Every IDE session talking to this MCP surface acts as this one, fixed
# actor — real stub-auth tier, same posture as Control UI's own
# dev-admin-token convention (Phase 24), not yet real per-user identity
# (Phase 31's own named scope). Real, tested authorize()+audit_log()
# calls happen for every tool regardless.
ACTOR = os.environ.get("MCP_SURFACE_ACTOR", "mcp_surface")
GATEWAY_TOKEN = os.environ.get("MCP_SURFACE_GATEWAY_TOKEN", "dev-mcp-surface-token")


def new_correlation_id() -> str:
    return str(uuid.uuid4())


def authorize(action: str, resource: str, correlation_id: str) -> dict:
    try:
        resp = httpx.post(
            f"{SECURITY_LAYER_URL}/security/authorize",
            json={"actor": ACTOR, "actor_type": "service", "action": action, "resource": resource, "correlation_id": correlation_id},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:  # noqa: BLE001 — fail closed
        return {"decision": "deny", "reason": f"security layer unreachable, failing closed: {e}"}


def audit_log(action: str, resource: str, decision: str, reason: str, correlation_id: str) -> None:
    try:
        httpx.post(
            f"{SECURITY_LAYER_URL}/audit/log",
            json={"actor_id": ACTOR, "actor_type": "service", "action": action, "resource": resource, "decision": decision, "reason": reason, "correlation_id": correlation_id},
            timeout=10.0,
        )
    except Exception:  # noqa: BLE001 — best-effort, same posture as every other client.py in this repo
        pass


def submit_task(title: str, description: str, correlation_id: str) -> dict:
    resp = httpx.post(
        f"{PLATFORM_URL}/api/v1/tasks",
        json={"title": title, "description": description, "context_refs": correlation_id},
        headers={"Authorization": f"Bearer {GATEWAY_TOKEN}"},
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


def get_task_status(task_id: str) -> dict | None:
    resp = httpx.get(f"{PLATFORM_URL}/api/v1/tasks/{task_id}", headers={"Authorization": f"Bearer {GATEWAY_TOKEN}"}, timeout=10.0)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def ask_agent(capability: str, question: str, correlation_id: str) -> dict:
    resp = httpx.post(
        f"{AGENTS_URL}/reasoning/execute",
        json={
            "task_id": f"mcp-ask-{correlation_id[:8]}", "task_description": question,
            "agent_capability": capability, "namespace": "default", "correlation_id": correlation_id,
        },
        timeout=120.0,  # a real reasoning execution — real model latency, not instant
    )
    resp.raise_for_status()
    return resp.json()


def search_knowledge(query: str, top_k: int) -> dict:
    resp = httpx.post(f"{KNOWLEDGE_URL}/vector/query", json={"text": query, "top_k": top_k}, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def get_erp_snapshots() -> dict:
    resp = httpx.get(f"{KNOWLEDGE_PIPELINES_URL}/erp-knowledge/snapshots", timeout=15.0)
    resp.raise_for_status()
    return resp.json()


def get_erp_graph(target_db: str, table: str = None) -> dict:
    params = {"target_db": target_db}
    if table:
        params["table"] = table
    resp = httpx.get(f"{KNOWLEDGE_PIPELINES_URL}/erp-knowledge/graph", params=params, timeout=15.0)
    resp.raise_for_status()
    return resp.json()


def list_pending_approvals() -> list:
    resp = httpx.get(f"{SECURITY_LAYER_URL}/approval/pending", timeout=10.0)
    resp.raise_for_status()
    return resp.json()


def get_audit_trail_by_correlation_id(correlation_id: str) -> list:
    resp = httpx.get(f"{SECURITY_LAYER_URL}/audit/query", params={"correlation_id": correlation_id}, timeout=10.0)
    resp.raise_for_status()
    return resp.json()


def list_capabilities() -> dict:
    resp = httpx.get(f"{PLANNING_URL}/capabilities", timeout=10.0)
    resp.raise_for_status()
    return resp.json()


def trigger_workflow(name: str, correlation_id: str) -> dict:
    """Phase 30: the real dispatch call for a saved workflow definition —
    Planning's own /workflows/{name}/trigger, which creates the real
    TaskGraph/Subtask rows and dispatches whatever steps are ready right
    now. Every step still runs through its own real governance gate when
    it dispatches; this tool only starts the run, same as ask_agent only
    starts one execution rather than granting anything."""
    resp = httpx.post(
        f"{PLANNING_URL}/workflows/{name}/trigger",
        json={"correlation_id": correlation_id},
        timeout=300.0,  # a real workflow's first wave of steps can complete synchronously inline
    )
    resp.raise_for_status()
    return resp.json()
