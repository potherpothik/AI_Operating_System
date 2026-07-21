# Claude Code

Add AIOS's MCP Surface as a project-scoped server:

```bash
claude mcp add --transport http aios http://localhost:8025/mcp
```

Or add it directly to a project's `.mcp.json`:

```json
{
  "mcpServers": {
    "aios": {
      "type": "http",
      "url": "http://localhost:8025/mcp"
    }
  }
}
```

Verify it connected with `/mcp` inside a Claude Code session — `aios`
should show as connected with 8 tools.

> Config field names for HTTP-transport MCP servers have shifted across
> Claude Code releases. This recipe reflects the CLI/`.mcp.json` shape
> current as of this phase's writing (Phase 26) but was not run through
> a live Claude Code session in this environment — verify against
> `claude mcp --help` if it doesn't connect on the first try.
