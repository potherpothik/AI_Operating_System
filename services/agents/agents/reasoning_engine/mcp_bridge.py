import json

from agents import clients

# Phase 26: closes the "MCP not real/wired" gap named in
# docs/requirements-alignment-assessment.md — extensibility's real MCP
# client (Phase 12: register -> approve -> activate -> invoke) has
# existed since Phase 12, but Reasoning Engine never called it. This is
# the wiring, not a new invocation mechanism — the real, already-tested
# /mcp/invoke endpoint does the actual work.
TOOL_ACTIONS = {"research.invoke_mcp_tool"}


def handle_tool_call(parsed: dict, agent_capability: str, task_id: str, correlation_id: str = None) -> dict:
    server_name = (parsed.get("mcp_server_name") or "").strip()
    tool_name = (parsed.get("mcp_tool_name") or "").strip()
    if not server_name:
        return {"summary": "mcp_server_name was empty — nothing to invoke"}
    if not tool_name:
        return {"summary": "mcp_tool_name was empty — nothing to invoke"}

    raw_params = parsed.get("mcp_params_json") or "{}"
    try:
        params = json.loads(raw_params)
    except json.JSONDecodeError as e:
        return {"summary": f"mcp_params_json was not valid JSON ({e})"}
    if not isinstance(params, dict):
        return {"summary": "mcp_params_json must be a JSON object"}

    servers = clients.mcp_list_servers()
    if not servers.get("ok"):
        return {"summary": f"could not reach extensibility's MCP client: {servers.get('error')}"}

    # Resolved by real name lookup against the real, active server list —
    # never a model-supplied internal id (same "the system computes the
    # real target, never trusts model input for it" discipline
    # execution_bridge.py's branch naming already established).
    match = next((s for s in servers.get("servers", []) if s["name"] == server_name and s["status"] == "active"), None)
    if not match:
        active_names = [s["name"] for s in servers.get("servers", []) if s["status"] == "active"]
        return {"summary": f"no active MCP server named {server_name!r} — real active servers right now: {active_names}"}

    result = clients.mcp_invoke(
        match["id"], tool_name, params, agent_capability,
        task_id=task_id, correlation_id=correlation_id or "",
    )
    if not result.get("ok"):
        return {"summary": f"mcp.invoke failed: {result.get('error')}"}

    return {"summary": f"tool {tool_name!r} on {server_name!r} returned: {json.dumps(result.get('result'))[:2000]}"}
