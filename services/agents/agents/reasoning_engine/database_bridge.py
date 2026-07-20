import json

from agents import clients

# Non-terminal actions: when Database Agent's response declares one of
# these, Reasoning Engine calls Database Connector directly, feeds the
# REAL result back into context, and continues iterating rather than
# finalizing — the two-step read/dry-run-then-decide pattern the Phase 7
# doc's Section 3 diagram describes. This is deliberately a small,
# explicitly-scoped mechanism for these two specific actions, not the
# fully generic tool-calling loop the original Phase 5 doc's
# "tool_call_request... extension point" language gestured at — that's a
# larger undertaking appropriately left to whichever future phase
# actually needs it for more than one agent.
TOOL_ACTIONS = {"db.read", "db.dry_run"}


def _parse_params(parsed: dict) -> tuple[dict, str | None]:
    raw = parsed.get("params_json") or "{}"
    try:
        return json.loads(raw), None
    except json.JSONDecodeError as e:
        return {}, f"params_json was not valid JSON ({e})"


def _parse_pii_fields(parsed: dict) -> tuple[list, str | None]:
    """
    Phase 15: an optional, additive field — only agents whose template
    actually instructs the model to name specific PII fields (Sales
    Agent) ever populate this; every other agent's db.read call leaves it
    unset and behaves exactly as before ([] requested, nothing PII-tagged
    included).
    """
    raw = parsed.get("pii_fields_requested_json") or "[]"
    try:
        fields = json.loads(raw)
    except json.JSONDecodeError as e:
        return [], f"pii_fields_requested_json was not valid JSON ({e})"
    if not isinstance(fields, list):
        return [], "pii_fields_requested_json must be a JSON array"
    return fields, None


def handle_tool_call(parsed: dict, agent_capability: str, task_id: str, correlation_id: str = None, requester_ceiling: str = "internal") -> dict:
    action = parsed.get("action")
    params, param_error = _parse_params(parsed)
    if param_error:
        return {"summary": param_error}

    if action == "db.read":
        pii_fields, pii_error = _parse_pii_fields(parsed)
        if pii_error:
            return {"summary": pii_error}
        result = clients.db_query(
            target_db=parsed.get("target_db") or "", table=parsed.get("table") or "",
            sql_template=parsed.get("sql_template") or "", params=params,
            capability=agent_capability, requesting_agent="reasoning_engine", task_id=task_id,
            correlation_id=correlation_id or "", pii_fields_requested=pii_fields,
            requester_ceiling=requester_ceiling,
        )
        if not result.get("ok"):
            return {"summary": f"read failed: {result.get('error')}"}
        return {"summary": f"{result['row_count']} row(s) returned: {result['rows']}"}

    if action == "db.dry_run":
        result = clients.db_dry_run(
            target_db=parsed.get("target_db") or "", sql_template=parsed.get("sql_template") or "", params=params,
            capability=agent_capability, requesting_agent="reasoning_engine", task_id=task_id,
            correlation_id=correlation_id or "",
        )
        if not result.get("ok"):
            return {"summary": f"dry-run failed: {result.get('error')}"}
        return {
            "summary": f"estimated {result['estimated_rows_affected']} row(s) affected ({result.get('plan_node_type', 'unknown')} query plan)",
            "dry_run_id": result["dry_run_id"],
        }

    return {"summary": f"unrecognized tool action {action!r}"}


def materialize_propose_write(execution) -> dict:
    """
    Called from resume() after a db.propose_write is approved. Requires a
    real dry_run_id captured during execute()'s own tool-call handling —
    Reasoning Engine tracks this itself rather than trusting the model to
    echo one back, since a model-supplied ID would be exactly the kind of
    untrusted self-report the rest of this system already refuses to
    trust (Phase 5 doc, Reasoning Engine security notes).
    """
    result = execution.result or {}
    dry_run_id = result.get("dry_run_id")
    if not dry_run_id:
        return {"attempted": False, "reason": "no dry_run_id recorded for this execution — a write cannot proceed without one"}

    params, param_error = _parse_params(result)
    if param_error:
        return {"attempted": False, "reason": param_error}

    write_result = clients.db_write(
        target_db=result.get("target_db") or "", sql_template=result.get("sql_template") or "", params=params,
        dry_run_id=dry_run_id, capability=execution.agent_capability, requesting_agent="reasoning_engine",
        task_id=execution.task_id, correlation_id=execution.id,
    )
    return {"attempted": True, "result": write_result}


def materialize_propose_migration(execution) -> dict:
    result = execution.result or {}
    target_platform = result.get("target_platform") or "django"
    migrate_result = clients.db_migrate(
        target_platform=target_platform, description=result.get("answer_or_proposal", ""),
        capability=execution.agent_capability, requesting_agent="reasoning_engine",
        task_id=execution.task_id, correlation_id=execution.id,
    )
    return {"attempted": True, "result": migrate_result}
