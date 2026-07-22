# Phase 26 — MCP Surface (working implementation)

Real, tested code. This is AIOS exposing itself TO an IDE — a genuine MCP
server (official `mcp` Python SDK, streamable HTTP transport) that Claude
Code, Cursor, VS Code+Continue, OpenCode, or any other MCP-speaking client
can connect to directly. It is the mirror image of Phase 12's MCP Client
(`services/extensibility/`), which is AIOS calling OUT to external MCP-shaped
servers — this is AIOS being called INTO. The two use different protocols
(this one speaks real MCP JSON-RPC 2.0; the Phase 12 client speaks a
deliberately simplified `{tool, params} -> {result}` REST contract) and
share no code.

Every tool call authorizes and audit-logs through the real Security Layer
before touching anything — the same discipline Control UI's BFF (Phase 24)
already established for the web operator console. There is no tool that can
decide a pending approval: `list_pending_approvals` is read-only, and
deciding stays in the AIOS web UI only. This is enforced structurally (no
such tool exists in `mcp_surface/server.py`) and by governance policy (the
`mcp_surface` role has no `approval.decide`-shaped action grant).

Actor identity is a fixed, stub-auth `mcp_surface` role — matching Control
UI's Phase 24 posture, explicitly not real per-user auth (deferred, per the
forward plan's own scope, to Phase 31).

## Its own isolated venv — do not install `mcp` into the shared venv

`pip install mcp` pulls in `starlette>=0.40`, which breaks every other
FastAPI-based service in this repo (`fastapi==0.115.0` requires
`starlette<0.39.0`). This was discovered live while building this phase:
installing `mcp` into the shared repo `.venv` upgraded starlette and broke
governance, platform-spine, knowledge, and every other FastAPI service with
`TypeError: Router.__init__() got an unexpected keyword argument
'on_startup'`. The fix was a downgrade + uninstall of `mcp` and its
transitive deps from the shared venv, and a hard rule going forward:
this service gets its own venv, never the shared one.

```bash
cd services/mcp-surface
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Run it

```bash
export SECURITY_LAYER_URL=http://localhost:8000
export PLATFORM_URL=http://localhost:8002       # task submission (Gateway)
export AGENTS_URL=http://localhost:8005         # ask_agent
export KNOWLEDGE_URL=http://localhost:8003      # search_knowledge, get_erp_schema
export KNOWLEDGE_PIPELINES_URL=http://localhost:8009
export PLANNING_URL=http://localhost:8008       # list_capabilities, trigger_workflow
.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8025
```

The MCP endpoint is `http://localhost:8025/mcp` (streamable HTTP — the
`mcp` SDK's own default path). `GET /healthz` is a plain liveness check.

## The 9 real tools

`submit_task`, `get_task_status`, `ask_agent`, `search_knowledge`,
`get_erp_schema`, `list_pending_approvals`, `get_audit_trail`,
`list_capabilities`, `trigger_workflow` (Phase 30 — starts a real, saved
declarative workflow by name) — see `mcp_surface/server.py` for each
tool's real docstring (the SDK surfaces these to the connecting IDE
directly).

## Test it

```bash
.venv/bin/python -m pytest tests/ -v
```

11 real tests — genuine `initialize`/`tools/list`/`tools/call` MCP JSON-RPC
round trips via the official `mcp` SDK's own client
(`mcp.client.streamable_http.streamablehttp_client` + `mcp.ClientSession`)
against the real running server and real backing services (governance,
platform-spine, knowledge), not direct Python function calls and not
mocked. `tests/live_smoke_test.py` is a standalone end-to-end script for
manual verification:

```bash
.venv/bin/python tests/live_smoke_test.py
```

## Connecting an IDE

See [`docs/ide-recipes/`](../../docs/ide-recipes/) for Claude Code, Cursor,
VS Code+Continue, and OpenCode connection recipes.

## Known limits (honest, not deferred silently)

- Auth is a fixed stub actor (`mcp_surface`), not per-user — every IDE
  session shares the same governance identity and the same audit trail
  actor. Real per-user auth is out of scope for this phase (Phase 31).
- `get_erp_schema` only returns schema for a target AIOS has already
  synced (Phase 9's ERP Knowledge Engine) — it never connects to a live
  ERP database directly.
