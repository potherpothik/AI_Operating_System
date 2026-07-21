# OpenCode

Add to `opencode.json` (project-scoped) or the global OpenCode config:

```json
{
  "mcp": {
    "aios": {
      "type": "remote",
      "url": "http://localhost:8025/mcp",
      "enabled": true
    }
  }
}
```

Run `opencode` and check its MCP status — `aios` should show as
connected with 8 tools available to the agent.

> Written from OpenCode's documented remote-MCP config shape current
> as of this phase's writing (Phase 26); not run through a live
> OpenCode session in this environment — this repo's own live testing
> of `coding_agent_gateway` (Phase 22) found OpenCode's sandbox-safety
> gate is separate from this and unaffected by it. Verify field names
> against OpenCode's own docs if the connection doesn't come up.
