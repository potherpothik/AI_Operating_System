from pathlib import Path

from agents import clients

TEMPLATE_ID = "odoo_agent"
TEMPLATE_PATH = Path(__file__).parent / "template.md"

# Flat type-name schema, matching assembly's schema_validate.py contract
# (assembly.prompt_builder.schema_validate.CANONICAL_SCHEMA) plus one
# Odoo-Agent-specific field ("action") used for capability-based
# authorization in the Reasoning Engine's routing logic.
EXPECTED_OUTPUT_SCHEMA = {
    "reasoning": "str",
    "answer_or_proposal": "str",
    "confidence": "float",
    "provenance": "list",
    "risk_classification": "str",
    "delegate_to": "optional_str",
    "action": "str",
    "odoo_model": "optional_str",
    "odoo_domain_json": "optional_str",
    "odoo_fields_json": "optional_str",
}


def ensure_template_registered(created_by: str = "odoo_agent_startup") -> dict:
    """
    Best-effort, idempotent: does nothing if an active or already-pending
    registration exists AND its body still matches the file on disk
    (Phase 26's own real fix — a changed template.md would otherwise
    silently never take effect once a template was already active, first
    hit when odoo_agent's own template changed in place for the first
    time since Phase 5, in this Phase 29). Template registration is
    approval-gated through governance (Phase 4 design) — this only files
    the request, a human still has to approve it via governance's
    /approval endpoints before Odoo Agent can actually run.
    """
    body = TEMPLATE_PATH.read_text()
    try:
        existing = clients.list_templates()
    except Exception as e:  # noqa: BLE001 — startup must never crash the service over an unreachable dependency
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
