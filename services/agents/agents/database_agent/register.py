from pathlib import Path

from agents import clients

TEMPLATE_ID = "database_agent"
TEMPLATE_PATH = Path(__file__).parent / "template.md"

# Flat type-name schema, matching assembly's schema_validate.py contract
# plus Database-Agent-specific fields used to drive the dry-run-before-
# write tool-call pattern in the Reasoning Engine (Phase 7 doc, Section 3).
EXPECTED_OUTPUT_SCHEMA = {
    "reasoning": "str",
    "answer_or_proposal": "str",
    "confidence": "float",
    "provenance": "list",
    "risk_classification": "str",
    "delegate_to": "optional_str",
    "action": "str",
    "target_db": "optional_str",
    "sql_template": "optional_str",
    "params_json": "optional_str",
    "table": "optional_str",
    "impact_estimate": "optional_str",
    "target_platform": "optional_str",
}


def ensure_template_registered(created_by: str = "database_agent_startup") -> dict:
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
