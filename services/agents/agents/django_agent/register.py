from pathlib import Path

from agents import clients

TEMPLATE_ID = "django_agent"
TEMPLATE_PATH = Path(__file__).parent / "template.md"

EXPECTED_OUTPUT_SCHEMA = {
    "reasoning": "str",
    "answer_or_proposal": "str",
    "confidence": "float",
    "provenance": "list",
    "risk_classification": "str",
    "delegate_to": "optional_str",
    "action": "str",
    "target_platform": "optional_str",
    "manage_py_command": "optional_str",
}


def ensure_template_registered(created_by: str = "django_agent_startup") -> dict:
    """Best-effort, idempotent — same pattern as odoo_agent/register.py,
    including its Phase 26 body-diff fix (this is the first time
    django_agent's own template body has changed since Phase 10)."""
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
