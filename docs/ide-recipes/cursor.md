# Cursor

Add to `.cursor/mcp.json` (project-scoped) or `~/.cursor/mcp.json`
(global):

```json
{
  "mcpServers": {
    "aios": {
      "url": "http://localhost:8025/mcp"
    }
  }
}
```

Open Cursor Settings → MCP to confirm `aios` shows as connected with 9
tools listed. If your Cursor version doesn't yet support a bare `url`
for streamable HTTP servers, check its MCP settings docs for the
current remote-server field name — this has changed across Cursor
releases.

> Written from Cursor's documented remote-MCP config shape current as
> of this phase's writing (Phase 26); not run through a live Cursor
> session in this environment.
