from pathlib import Path

from agents import clients

TEMPLATE_ID = "research_agent"
TEMPLATE_PATH = Path(__file__).parent / "template.md"

EXPECTED_OUTPUT_SCHEMA = {
    "reasoning": "str",
    "answer_or_proposal": "str",
    "confidence": "float",
    "provenance": "list",
    "risk_classification": "str",
    "delegate_to": "optional_str",
    "action": "str",
    "mcp_server_name": "optional_str",
    "mcp_tool_name": "optional_str",
    "mcp_params_json": "optional_str",
}


def ensure_template_registered(created_by: str = "research_agent_startup") -> dict:
    """Best-effort, idempotent — same pattern as odoo_agent/register.py,
    plus a body-diff check (Phase 26): the first time an existing agent's
    template body changed in place (research.invoke_mcp_tool added to an
    already-active template from Phase 18) rather than a brand-new agent
    being registered for the first time. Without this, a changed
    template.md would silently never take effect — the old status-only
    check treated "already active" as "nothing to do" regardless of body."""
    body = TEMPLATE_PATH.read_text()
    try:
        existing = clients.list_templates()
    except Exception as e:  # noqa: BLE001
        return {"registered": False, "reason": f"assembly unreachable: {e}"}

    for t in existing:
        if t["agent_template_id"] == TEMPLATE_ID and t["status"] in ("active", "pending_approval"):
            if t["status"] == "active" and t.get("body") != body:
                break  # active but stale — fall through and register a new version
            return {"registered": False, "reason": f"already {t['status']}", "template": t}

    try:
        result = clients.register_template(TEMPLATE_ID, body, EXPECTED_OUTPUT_SCHEMA, created_by)
    except Exception as e:  # noqa: BLE001
        return {"registered": False, "reason": f"registration call failed: {e}"}
    return {"registered": True, "result": result}
