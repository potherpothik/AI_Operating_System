"""
Phase 26 — MCP Surface. Real MCP server (official `mcp` SDK, streamable
HTTP transport), exposing this system's governed agents/knowledge/
approvals as MCP tools an IDE can call directly. A thin translator, never
a bypass: every tool call authorizes and audit-logs through the real
Security Layer (services/governance/) before touching anything, exactly
the same discipline Control UI's BFF (Phase 24) already established for
the web operator console.

Deliberately excluded: any tool that could DECIDE an approval. An
AI-driven IDE session must never be able to approve its own risky
actions — `list_pending_approvals` is read-only; deciding stays in the
web UI (services/control-ui/, Phase 24) only. There is no
`decide_approval` tool anywhere in this file, and no governance role
grant that would make one meaningful even if added by mistake later
(services/governance/governance/security/policies/default.yaml's
`mcp_surface` role has no approval.decide-shaped action).
"""

from mcp.server.fastmcp import FastMCP

from mcp_surface import clients

mcp = FastMCP(
    name="aios",
    instructions=(
        "AI Operating System governed tool surface. Every tool call is authorized "
        "and audit-logged by the real Security Layer before it runs. This surface "
        "cannot approve pending approvals — that only happens in the AIOS web UI."
    ),
    host="0.0.0.0",
    port=8025,
)


def _gate(action: str, resource: str):
    """Real authorize()+audit_log() call, shared by every tool below —
    the actual gate, not decoration. Returns the correlation_id to thread
    through the rest of the tool call, or raises PermissionError if
    Security Layer denies (or is unreachable — fails closed)."""
    correlation_id = clients.new_correlation_id()
    decision = clients.authorize(action, resource, correlation_id)
    if decision["decision"] == "deny":
        clients.audit_log(action, resource, "deny", decision.get("reason", ""), correlation_id)
        raise PermissionError(f"denied by AIOS Security Layer: {decision.get('reason', 'no reason given')}")
    clients.audit_log(action, resource, "allow", "", correlation_id)
    return correlation_id


@mcp.tool()
def submit_task(title: str, description: str = "") -> dict:
    """Submit a new task to AIOS's real task queue (the same governed path
    the AIOS web UI uses) — an agent will pick it up asynchronously. Returns
    the created task, including its id for get_task_status."""
    correlation_id = _gate("mcp_surface.submit_task", title)
    return clients.submit_task(title, description, correlation_id)


@mcp.tool()
def get_task_status(task_id: str) -> dict:
    """Look up the real, current status of a task previously created by
    submit_task (or by any other real AIOS caller)."""
    _gate("mcp_surface.get_task_status", task_id)
    result = clients.get_task_status(task_id)
    if result is None:
        raise ValueError(f"no task with id {task_id!r}")
    return result


@mcp.tool()
def ask_agent(capability: str, question: str) -> dict:
    """Ask one of AIOS's real governed agents (e.g. odoo_agent, python_agent,
    security_agent — see list_capabilities for the real, current roster) a
    question and wait for its real answer. This blocks for real model
    inference time. Mutating proposals still require human approval in the
    AIOS web UI before anything is committed — this tool never bypasses that."""
    correlation_id = _gate("mcp_surface.ask_agent", capability)
    return clients.ask_agent(capability, question, correlation_id)


@mcp.tool()
def search_knowledge(query: str, top_k: int = 5) -> dict:
    """Semantic search over AIOS's real ingested knowledge base (Vector
    Search, Phase 3/25 — real embeddings, not keyword match)."""
    _gate("mcp_surface.search_knowledge", query)
    return clients.search_knowledge(query, top_k)


@mcp.tool()
def get_erp_schema(target_db: str = "", table: str = "") -> dict:
    """Real ERP database schema knowledge. Omit target_db to list every
    target AIOS has ever synced schema for; pass a target_db (and
    optionally a table) to get that target's real, current schema graph."""
    _gate("mcp_surface.get_erp_schema", target_db or "*")
    if not target_db:
        return clients.get_erp_snapshots()
    return clients.get_erp_graph(target_db, table or None)


@mcp.tool()
def list_pending_approvals() -> dict:
    """Real, currently-pending approval requests awaiting a human decision
    in the AIOS web UI. Read-only — this tool cannot decide them; only a
    human in the web UI can."""
    _gate("mcp_surface.list_pending_approvals", "*")
    approvals = clients.list_pending_approvals()
    # Wrapped in a dict key, matching this system's own established
    # convention for every other list-returning endpoint (e.g.
    # {"hits": [...]}, {"capabilities": [...]}) — also avoids a real
    # MCP SDK behavior found live: a bare list return type gets
    # serialized as N separate content blocks, one per item, not one
    # JSON array in a single block.
    return {"approvals": approvals}


@mcp.tool()
def get_audit_trail(task_id: str) -> dict:
    """The real, complete audit trail for one task — every authorize
    decision, every governed action, in order. Resolves the task's own
    correlation_id first, then queries the real hash-chained audit log
    (Phase 1) by it."""
    _gate("mcp_surface.get_audit_trail", task_id)
    task = clients.get_task_status(task_id)
    if task is None:
        raise ValueError(f"no task with id {task_id!r}")
    correlation_id = task.get("correlation_id")
    events = clients.get_audit_trail_by_correlation_id(correlation_id) if correlation_id else []
    return {"task_id": task_id, "correlation_id": correlation_id, "events": events}


@mcp.tool()
def list_capabilities() -> dict:
    """The real, current roster of AIOS agent capabilities (Capability
    Registry, Phase 8) — what an IDE can legitimately ask_agent about."""
    _gate("mcp_surface.list_capabilities", "*")
    return clients.list_capabilities()


@mcp.tool()
def trigger_workflow(name: str) -> dict:
    """Trigger a real, saved AIOS workflow (Phase 30 Declarative Workflows
    — e.g. code_review_pipeline) by name. Starts a real multi-step run:
    creates the task graph, dispatches whatever steps have no
    dependencies right now, and returns the run's real task_graph_id for
    checking status later via Planning's GET /workflows/runs/{id}. Every
    step still goes through its own independent governance gate when it
    dispatches — this tool never pre-grants consent for the whole run."""
    correlation_id = _gate("mcp_surface.trigger_workflow", name)
    return clients.trigger_workflow(name, correlation_id)
