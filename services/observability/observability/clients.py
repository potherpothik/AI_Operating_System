import os
import httpx

from observability.registry import service_url

DEFAULT_TIMEOUT = 5.0

# Phase 2's Gateway requires a bearer token on every /api/v1/tasks call
# (resolve_actor) — there is no distinct "read-only viewer" role in
# tokens.yaml, only the same stub token→role file every other phase
# already documents as standing in for real SSO/LDAP (Phase 2 doc). Using
# the admin token here is the honest reflection of that gap, not a
# privilege escalation this phase invents: Health Monitor and Metrics
# Dashboard are human-facing operational views with no write path of
# their own regardless of which token resolves them.
GATEWAY_TOKEN = os.environ.get("GATEWAY_TOKEN", "dev-admin-token")
_AUTH_HEADERS = {"Authorization": f"Bearer {GATEWAY_TOKEN}"}


def poll_health(name: str, url: str) -> dict:
    """
    Tries GET /healthz first (what most services expose), falls back to
    GET / (governance, assembly, planning, extensibility, database,
    knowledge, knowledge_pipelines, execution all answer this too — see
    each service's own main.py). A single unreachable service returns
    'down' here; it never raises, so one dead peer can't blind the
    caller to every other service's status (doc, Health Monitor failure
    handling).
    """
    for path in ("/healthz", "/"):
        try:
            resp = httpx.get(f"{url}{path}", timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 200:
                return {"name": name, "url": url, "status": "up", "detail": resp.json()}
        except Exception:  # noqa: BLE001
            continue
    return {"name": name, "url": url, "status": "down", "detail": None}


def audit_log(actor_id: str, action: str, resource: str, decision: str = "recorded", reason: str = "") -> bool:
    governance_url = service_url("governance")
    try:
        resp = httpx.post(
            f"{governance_url}/audit/log",
            json={"actor_id": actor_id, "actor_type": "service", "action": action, "resource": resource, "decision": decision, "reason": reason},
            timeout=DEFAULT_TIMEOUT,
        )
        return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def get_tasks(status: str = None) -> list:
    try:
        params = {"status": status} if status else {}
        resp = httpx.get(f"{service_url('platform-spine')}/api/v1/tasks", params=params, headers=_AUTH_HEADERS, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception:  # noqa: BLE001
        return []


def get_reasoning_executions(status: str = None, agent_capability: str = None) -> list:
    try:
        params = {}
        if status:
            params["status"] = status
        if agent_capability:
            params["agent_capability"] = agent_capability
        resp = httpx.get(f"{service_url('agents')}/reasoning/executions", params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception:  # noqa: BLE001
        return []


def get_erp_snapshots() -> list:
    try:
        resp = httpx.get(f"{service_url('knowledge_pipelines')}/erp-knowledge/snapshots", timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception:  # noqa: BLE001
        return []


def get_approvals(status: str = None) -> list:
    try:
        params = {"status": status} if status else {}
        resp = httpx.get(f"{service_url('governance')}/approval", params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception:  # noqa: BLE001
        return []


def get_pending_approvals() -> list:
    try:
        resp = httpx.get(f"{service_url('governance')}/approval/pending", timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception:  # noqa: BLE001
        return []


def get_shell_executions(requesting_capability: str = None, status: str = None) -> list:
    try:
        params = {}
        if requesting_capability:
            params["requesting_capability"] = requesting_capability
        if status:
            params["status"] = status
        resp = httpx.get(f"{service_url('execution')}/shell/executions", params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception:  # noqa: BLE001
        return []


def get_db_query_log(capability: str = None) -> list:
    try:
        params = {"capability": capability} if capability else {}
        resp = httpx.get(f"{service_url('database')}/db/query-log", params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception:  # noqa: BLE001
        return []


def get_vector_stats() -> dict:
    try:
        resp = httpx.get(f"{service_url('knowledge')}/vector/stats", timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception:  # noqa: BLE001
        return {}
