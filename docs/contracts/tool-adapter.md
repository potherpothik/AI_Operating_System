# `ToolAdapter` contract — v1

Formalizes the shape every real tool-calling service in this system
already follows — `services/execution/` (Phase 6), `services/database/`
(Phase 7), and `services/extensibility/`'s MCP Client (Phase 12). Not a
new Python base class (these are separate FastAPI services, not one
shared codebase) — a **structural** contract every one of them already
satisfies, made explicit so a new tool adapter (Phase 29's browser/
live-Odoo/live-Django adapters) is built to the same shape from day one.

## The shape

1. **A real, narrow action surface.** Not a generic "run anything"
   endpoint — Shell Executor's `POST /execute` still only runs an
   allowlisted command with allowlisted args (`services/execution/execution/shell_executor/sandbox.py`);
   Database Connector's `POST /db/read`/`/dry_run`/`/propose_write` are
   three distinct, narrow operations, never one raw-SQL passthrough.
2. **Governance-gated per call, always.** Every real tool call
   authorizes (`POST /security/authorize`) and audit-logs
   (`POST /audit/log`) against the real capability making the call —
   never a blanket "the service is reachable, so it's allowed" check.
   Confirmed structurally: every adapter service's own test suite
   includes a real "denied for a capability with no policy role" case
   (e.g. `services/extensibility/tests/test_mcp_client.py::test_invoke_denied_for_a_capability_with_no_policy_role`).
3. **Mutating actions are propose-then-approve, read actions are not.**
   Shell Executor's `mode="read_only"` vs a mutating command; Database
   Connector's `db.read` (no approval) vs `db.propose_write` (requires
   an already-run `db.dry_run`, requires human approval); Git Manager's
   `branch`/`commit`/`push` all real but `open_mr` is the human-facing
   review point, never an auto-merge.
4. **A registry, not a hardcoded allowlist inside agent code.** The
   individual TARGET is registered and approval-gated once (Shell
   Executor's per-capability command allowlists in
   `services/execution/execution/shell_executor/allowlists/`, Database
   Connector's `secrets_registry.yaml` target-to-credential mapping,
   MCP Client's real `POST /mcp/register` → human approval →
   `POST /servers/{id}/activate` flow) — agent code never embeds a raw
   external endpoint or credential itself.
5. **Reached only through `agents/clients.py`**, never a bespoke
   `httpx` call inside a `*_bridge.py` or agent capability module — the
   same "no bespoke third-party calls" rule this phase's
   `test_adapter_boundary.py` now enforces (see `docs/contracts/README.md`).

## Real implementations (v1)

| Adapter | Narrow actions | Approval-gated mutation |
|---|---|---|
| Shell Executor | `execute` (allowlisted command+args) | Sandbox backend structurally verified per Phase 22's own gate |
| Git Manager | `branch`, `commit`, `diff`, `push`, `open_mr` | `open_mr` is the human review point |
| Database Connector | `db.read`, `db.dry_run`, `db.propose_write`, `db.propose_migration` | `propose_write` requires a prior `dry_run` in the same execution |
| MCP Client | `mcp.invoke` against an already-registered server | Registration itself is unconditionally approval-gated (Phase 12) |

## Consumers (v1)

Every Reasoning Engine bridge (`services/agents/agents/reasoning_engine/*_bridge.py`)
— `database_bridge.py`, `shell_bridge.py`, `execution_bridge.py`,
`mcp_bridge.py`, and the deterministic-script bridges (`calc_bridge.py`,
`cutlist_bridge.py`, `autocad_bridge.py`) — all reach their target
adapter exclusively through `agents/clients.py`'s wrapper functions.

## Versioning

v1 = the shape as it exists after Phase 27's adapters. Phase 29's new
adapters (browser, live Odoo, live Django) are the first real test of
whether this shape generalizes to genuinely new tool types without a
breaking change.
