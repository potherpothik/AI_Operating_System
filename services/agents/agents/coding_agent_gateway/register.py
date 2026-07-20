from pathlib import Path

from agents import clients

TEMPLATE_ID = "coding_agent_gateway"
TEMPLATE_PATH = Path(__file__).parent / "template.md"

EXPECTED_OUTPUT_SCHEMA = {
    "reasoning": "str",
    "answer_or_proposal": "str",
    "confidence": "float",
    "provenance": "list",
    "risk_classification": "str",
    "delegate_to": "optional_str",
    "action": "str",
    "provider": "str",
    "instruction": "str",
}


def ensure_template_registered(created_by: str = "coding_agent_gateway_startup") -> dict:
    """Best-effort, idempotent — same pattern as odoo_agent/register.py."""
    try:
        existing = clients.list_templates()
    except Exception as e:  # noqa: BLE001
        return {"registered": False, "reason": f"assembly unreachable: {e}"}

    for t in existing:
        if t["agent_template_id"] == TEMPLATE_ID and t["status"] in ("active", "pending_approval"):
            return {"registered": False, "reason": f"already {t['status']}", "template": t}

    body = TEMPLATE_PATH.read_text()
    try:
        result = clients.register_template(TEMPLATE_ID, body, EXPECTED_OUTPUT_SCHEMA, created_by)
    except Exception as e:  # noqa: BLE001
        return {"registered": False, "reason": f"registration call failed: {e}"}
    return {"registered": True, "result": result}
