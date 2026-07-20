from agents import clients

# Phase 18: Security Agent's real, non-terminal tool call — a genuine
# audit trail, never a model's guess about what "probably" happened.
# Mirrors database_bridge.py's exact shape.
TOOL_ACTIONS = {"security.audit_query"}


def handle_tool_call(parsed: dict, agent_capability: str, task_id: str, correlation_id: str = None) -> dict:
    action = parsed.get("action")
    if action != "security.audit_query":
        return {"summary": f"unrecognized tool action {action!r}"}

    audit_correlation_id = (parsed.get("audit_correlation_id") or "").strip()
    audit_actor_id = (parsed.get("audit_actor_id") or "").strip()
    audit_action = (parsed.get("audit_action") or "").strip()

    result = clients.audit_query(
        actor_id=audit_actor_id or None, action=audit_action or None, correlation_id=audit_correlation_id or None,
    )
    if not result.get("ok"):
        return {"summary": f"audit query failed: {result.get('error')}"}

    events = result["events"]
    return {"summary": f"{len(events)} real audit event(s) found: {events}"}
