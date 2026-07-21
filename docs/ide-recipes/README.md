# IDE Recipes — connecting to AIOS's MCP Surface

`services/mcp-surface/` (Phase 26) exposes 8 governed AIOS tools —
`submit_task`, `get_task_status`, `ask_agent`, `search_knowledge`,
`get_erp_schema`, `list_pending_approvals`, `get_audit_trail`,
`list_capabilities` — over real MCP (streamable HTTP transport) at
`http://localhost:8025/mcp`. Any MCP-speaking IDE or agent client can
connect. Every call still authorizes and audit-logs through the real
Security Layer — connecting an IDE does not grant it anything Security
Layer wouldn't otherwise allow the `mcp_surface` actor.

Start the server first (see [`services/mcp-surface/README.md`](../../services/mcp-surface/README.md)),
then pick your client below:

- [Claude Code](claude-code.md)
- [Cursor](cursor.md)
- [VS Code + Continue](vscode-continue.md)
- [OpenCode](opencode.md)

## Before you connect, know the limits

- `list_pending_approvals` is read-only — no tool here can approve
  anything. Deciding an approval still requires a human in the AIOS web
  UI (`services/control-ui/`, Phase 24).
- Every session authenticates as the same fixed `mcp_surface` actor —
  there's no per-user identity yet (Phase 31 territory). Every audit log
  entry from an MCP session shows `mcp_surface`, not who was actually
  typing.
- `submit_task`/`ask_agent` can take real model-inference time to
  respond — this isn't a local, instant tool call.
