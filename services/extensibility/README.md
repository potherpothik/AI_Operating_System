# Phase 12 — MCP Client & Plugin System (working implementation)

Real, tested code. The system's first two extensibility mechanisms: MCP
Client lets the orchestration layer consume external MCP-shaped tool
servers without a bespoke connector per integration; Plugin System lets
a new agent be added — a real `capability.yaml` + `template.md`, the
same shape every built-in agent since Phase 5 has — without modifying
any core code. Both are new tool/capability *sources*, not new trust
boundaries: every MCP invocation and every plugin's declared permissions
still route through the same Security Layer authorize + Human Approval
Layer gating everything else in this system goes through.

## Run it

```bash
pip install -r requirements.txt
export SECURITY_LAYER_URL=http://localhost:8000
export ASSEMBLY_URL=http://localhost:8004   # Plugin System registers a plugin's template with Prompt Builder
export AGENTS_URL=http://localhost:8005     # Plugin System triggers a hot capability reload here after activation
uvicorn main:app --port 8010
```

Plugin System writes an approved plugin's `capability.yaml`/`template.md`
to `PLUGIN_CAPABILITIES_DIR` (default `/tmp/ai_os_plugins`) — **this must
be the SAME path the `agents` service's own `PLUGIN_CAPABILITIES_DIR`
env var points at**, the same shared-path convention Phase 6/7's
`SANDBOX_ROOT` already established across two separate processes:

```bash
# both services need this set to the SAME directory
export PLUGIN_CAPABILITIES_DIR=/tmp/ai_os_plugins
```

Without it, a plugin still installs and gets approved, but never
actually becomes runnable — `capability_registry.py`'s discovery simply
finds nothing at the default path if the two services disagree on it.

## Test it

```bash
pytest tests/ -v   # no PHASE*_PATH needed for the pure adapter test;
                    # everything else auto-starts governance/platform/knowledge/assembly/agents
                    # via PHASE1_PATH..PHASE5_PATH if not already running
```

25 tests, all passing against a real local stub HTTP server (MCP Client)
and a real live `agents` service (Plugin System) — not mocked. The stub
server is a genuine `http.server.HTTPServer` on a real socket in a
background thread (`tests/conftest.py`), not a mocked `httpx` call.

## What's real

- **MCP Client's register → approve → activate → invoke lifecycle is
  real, end to end.** Registration is unconditionally approval-gated
  (never conditioned on who's asking, same posture as Documentation
  Engine's `classify-override`), and a genuine HTTP round trip against
  the real stub server proves the wiring — confirmed live: `invoke`
  against an unreachable server raises `ServerUnreachable` rather than
  fabricating a result, and a result missing a declared schema field
  raises `SchemaViolation` rather than being silently accepted.
- **Every invocation is recorded regardless of outcome** — confirmed by
  querying `McpInvocation` directly after a real call, not just trusting
  the HTTP response.
- **Plugin System's manifest validation is structural, not cosmetic**:
  a `required_permissions` entry outside the known, explicit
  `KNOWN_PERMISSIONS` set (`manifest.py`) is rejected at install time,
  before a governance approval request is even created — confirmed live
  that the plugin never reaches the store at all in that case. A
  malformed `capability.yaml` (bad YAML, or missing the required
  `capability` key) is rejected the same way, with a specific reason,
  not an opaque failure deep inside `capability_registry.py` later.
- **An approved plugin is genuinely discoverable by a live `agents`
  service — proven live, not by inspection.** `installer.py` writes a
  real `capability.yaml` to `PLUGIN_CAPABILITIES_DIR`, registers the
  template with Prompt Builder (itself still its own separate approval
  gate — a plugin gets no shortcut around that), and triggers
  `POST /capabilities/reload`; confirmed by then calling `GET
  /capabilities` on the real, already-running `agents` service and
  finding the new capability there — "adding new agents... without
  modifying core code" (doc) tested as a genuine claim, not an
  assertion.
- **Auto-disable past an error threshold is real**, confirmed live at
  exactly the boundary: `ERROR_THRESHOLD - 1` reports leave a plugin
  active, the `ERROR_THRESHOLD`th disables it — not "roughly around
  there."

## What's a stub or simplified

- **MCP Client speaks a deliberately simplified REST contract
  (`POST {server_url}/invoke` → `{"result": ...}`), not full MCP
  JSON-RPC 2.0** (stdio transport, `initialize`/`list_tools`/`call_tool`
  session lifecycle, capability negotiation). The same "real but
  reduced, honestly labeled" posture as Phase 3's `HashingEmbedding` and
  Phase 6's `SubprocessSandbox` — a server speaking this simpler
  contract works against `adapter.py` unchanged; swapping in a real
  JSON-RPC/stdio transport is a contained change to that one file, not
  an architecture change.
- **Plugin System's auto-disable hook
  (`POST /plugins/{id}/report-error`) is not yet wired to fire
  automatically from a failed Reasoning Engine execution.** The
  threshold mechanism itself is real and independently tested against
  direct calls; connecting it to a live capability's actual runtime
  failures is a real, small, well-scoped future integration — the same
  class of honestly-deferred wiring as Phase 9's poll-triggered "watch"
  mechanism.
- **`KNOWN_PERMISSIONS` (`manifest.py`) is a static, version-controlled
  set**, not derived dynamically from governance's live policy at
  install time — deliberate, so installation validity doesn't depend on
  a network call succeeding, but it does mean this list needs a manual
  update whenever a genuinely new system action is introduced elsewhere
  (same maintenance burden Shell Executor's own allowlist files already
  have).
- **No MCP server or plugin marketplace/catalog** — explicit
  out-of-scope per the doc; both are named future extension points.

## Next

Phase 13: Metrics Dashboard, Health Monitor — read-only aggregation over
data every prior phase already produces, deferred until there was
enough agent usage variety (Phase 10) to make a dashboard meaningful.
