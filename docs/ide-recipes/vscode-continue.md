# VS Code + Continue

Add to Continue's `config.yaml` (`~/.continue/config.yaml`, or a
workspace-local `.continue/config.yaml`):

```yaml
mcpServers:
  - name: aios
    type: streamable-http
    url: http://localhost:8025/mcp
```

Reload the Continue extension window, then check its MCP servers panel
— `aios` should list all 8 tools (`submit_task`, `get_task_status`,
`ask_agent`, `search_knowledge`, `get_erp_schema`,
`list_pending_approvals`, `get_audit_trail`, `list_capabilities`).

> Written from Continue's documented `mcpServers` config shape current
> as of this phase's writing (Phase 26); not run through a live VS
> Code + Continue session in this environment. If `type: streamable-http`
> isn't recognized by your Continue version, check whether it still
> expects `type: sse` for HTTP-based MCP servers.
