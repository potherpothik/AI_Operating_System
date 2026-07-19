from pathlib import Path

from agents import clients

TEMPLATE_ID = "costing_agent"
TEMPLATE_PATH = Path(__file__).parent / "template.md"

EXPECTED_OUTPUT_SCHEMA = {
    "reasoning": "str",
    "answer_or_proposal": "str",
    "confidence": "float",
    "provenance": "list",
    "risk_classification": "str",
    "delegate_to": "optional_str",
    "action": "str",
    "formula_name": "optional_str",
    "formula_ref": "optional_str",
    "target_namespace": "optional_str",
}


def ensure_template_registered(created_by: str = "costing_agent_startup") -> dict:
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
