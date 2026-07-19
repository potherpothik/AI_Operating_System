import os
import httpx

ASSEMBLY_URL = os.environ.get("ASSEMBLY_URL", "http://localhost:8004")
PLATFORM_URL = os.environ.get("PLATFORM_URL", "http://localhost:8002")
SECURITY_LAYER_URL = os.environ.get("SECURITY_LAYER_URL", "http://localhost:8000")
EXECUTION_URL = os.environ.get("EXECUTION_URL", "http://localhost:8006")
GATEWAY_TOKEN = os.environ.get("GATEWAY_TOKEN", "dev-odoo-agent-token")


def build_context(task_id: str, task_description: str, agent_capability: str, target_model: str, namespace: str, budget_words: int = None) -> dict:
    body = {
        "task_id": task_id, "task_description": task_description, "agent_capability": agent_capability,
        "target_model": target_model, "namespace": namespace,
    }
    if budget_words is not None:
        body["budget_words"] = budget_words
    resp = httpx.post(f"{ASSEMBLY_URL}/context/build", json=body, timeout=15.0)
    resp.raise_for_status()
    return resp.json()


def get_context(context_id: str) -> dict:
    resp = httpx.get(f"{ASSEMBLY_URL}/context/{context_id}", timeout=10.0)
    resp.raise_for_status()
    return resp.json()


class NoActiveTemplate(Exception):
    pass


class PromptTooLarge(Exception):
    pass


def render_prompt(context_package: dict, context_items: list, task_description: str, agent_template_id: str, target_model: str, max_prompt_words: int = 4000) -> dict:
    resp = httpx.post(
        f"{ASSEMBLY_URL}/prompt/render",
        json={
            "context_package": context_package, "context_items": context_items, "task_description": task_description,
            "agent_template_id": agent_template_id, "target_model": target_model, "max_prompt_words": max_prompt_words,
        },
        timeout=15.0,
    )
    if resp.status_code == 404:
        raise NoActiveTemplate(resp.json().get("detail", "no active template"))
    if resp.status_code == 413:
        raise PromptTooLarge(resp.json().get("detail", "prompt too large"))
    resp.raise_for_status()
    return resp.json()


def validate_response(raw_response: str, expected_output_schema: dict) -> dict:
    resp = httpx.post(
        f"{ASSEMBLY_URL}/prompt/validate-response",
        json={"raw_response": raw_response, "expected_output_schema": expected_output_schema},
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()


def register_template(agent_template_id: str, body: str, expected_output_schema: dict, created_by: str) -> dict:
    resp = httpx.post(
        f"{ASSEMBLY_URL}/prompt/templates",
        json={"agent_template_id": agent_template_id, "body": body, "expected_output_schema": expected_output_schema, "created_by": created_by},
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()


def list_templates() -> list:
    resp = httpx.get(f"{ASSEMBLY_URL}/prompt/templates", timeout=10.0)
    resp.raise_for_status()
    return resp.json()


def authorize(actor: str, action: str, resource: str, correlation_id: str = "") -> dict:
    try:
        resp = httpx.post(
            f"{SECURITY_LAYER_URL}/security/authorize",
            json={"actor": actor, "actor_type": "agent", "action": action, "resource": resource, "correlation_id": correlation_id},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:  # noqa: BLE001 — fail closed: an unreachable Security Layer must never be read as "allow"
        return {"decision": "deny", "reason": f"security layer unreachable, failing closed: {e}"}


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


def get_reasoning_engine_config() -> dict:
    try:
        resp = httpx.get(f"{PLATFORM_URL}/config/reasoning_engine", timeout=10.0)
        resp.raise_for_status()
        return resp.json()
    except Exception:  # noqa: BLE001 — fail toward the most restrictive assumption, same pattern as assembly/clients.py
        return {"external_model_allowed": False, "default_local_model": None, "fallback_local_model": None, "max_iterations": 8}


def create_delegate_task(title: str, description: str, correlation_id: str = "") -> dict:
    """Hands a task to Task Manager for a capability that doesn't exist yet (Phase 5 doc, Section 3)."""
    try:
        resp = httpx.post(
            f"{PLATFORM_URL}/api/v1/tasks",
            json={"title": title, "description": description, "priority": "normal", "context_refs": correlation_id},
            headers={"Authorization": f"Bearer {GATEWAY_TOKEN}"},
            timeout=10.0,
        )
        resp.raise_for_status()
        task = resp.json()
        httpx.post(
            f"{PLATFORM_URL}/api/v1/tasks/{task['id']}/status",
            json={"status": "needs_clarification", "detail": f"needs_agent:{description}"},
            headers={"Authorization": f"Bearer {GATEWAY_TOKEN}"},
            timeout=10.0,
        )
        return task
    except Exception as e:  # noqa: BLE001
        return {"id": None, "error": str(e)}


def git_branch(repo: str, agent_capability: str, task_id: str, requesting_agent: str, correlation_id: str = "") -> dict:
    try:
        resp = httpx.post(
            f"{EXECUTION_URL}/git/branch",
            json={"repo": repo, "agent_capability": agent_capability, "task_id": task_id, "requesting_agent": requesting_agent, "correlation_id": correlation_id},
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:  # noqa: BLE001
        return {"status": "failed", "result": {"reason": str(e)}}


def git_commit(repo: str, agent_capability: str, task_id: str, requesting_agent: str, files_changed: list, summary: str,
               reasoning_execution_id: str = None, context_id: str = None, correlation_id: str = "") -> dict:
    try:
        resp = httpx.post(
            f"{EXECUTION_URL}/git/commit",
            json={
                "repo": repo, "agent_capability": agent_capability, "task_id": task_id, "requesting_agent": requesting_agent,
                "files_changed": files_changed, "summary": summary, "reasoning_execution_id": reasoning_execution_id,
                "context_id": context_id, "correlation_id": correlation_id,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:  # noqa: BLE001
        return {"status": "failed", "result": {"reason": str(e)}}


def git_push(repo: str, agent_capability: str, task_id: str, requesting_agent: str, branch_name: str, correlation_id: str = "") -> dict:
    try:
        resp = httpx.post(
            f"{EXECUTION_URL}/git/push",
            json={"repo": repo, "agent_capability": agent_capability, "task_id": task_id, "requesting_agent": requesting_agent, "branch_name": branch_name, "correlation_id": correlation_id},
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:  # noqa: BLE001
        return {"status": "failed", "result": {"reason": str(e)}}


def git_open_mr(repo: str, branch_name: str, agent_capability: str, task_id: str, requesting_agent: str,
                proposal_text: str, risk_classification: str, files_changed: list = None, correlation_id: str = "") -> dict:
    try:
        resp = httpx.post(
            f"{EXECUTION_URL}/git/open_mr",
            json={
                "repo": repo, "branch_name": branch_name, "agent_capability": agent_capability, "task_id": task_id,
                "requesting_agent": requesting_agent, "proposal_text": proposal_text, "risk_classification": risk_classification,
                "files_changed": files_changed or [], "correlation_id": correlation_id,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:  # noqa: BLE001
        return {"status": "failed", "result": {"reason": str(e)}}
