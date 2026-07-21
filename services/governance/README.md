# Phase 1 — Governance Layer (working implementation)

Security Layer, Audit Logger, and Human Approval Layer from the design roadmap,
as real, tested code rather than a specification. Every endpoint described in
the Phase 1 design doc is implemented and covered by a passing test.

## Run it

```bash
pip install -r requirements.txt
uvicorn main:app --reload
# → http://127.0.0.1:8000
```

## Test it

```bash
pytest tests/ -v
```

47 tests, all passing (grown from the original 11 across every phase
since — secrets resolution, environment verification, the Phase 13
general approval listing, Phase 16's approval-review attachment, and
Phase 18's `correlation_id` audit filter are the most recent additions):
default-deny on unknown roles,
allow/deny/require_approval routing, every decision logged, the audit
hash chain validating correctly *and* correctly detecting a tampered
row, and the full approval request → pending → decide lifecycle
including rejection and expiry.

## Try it live

```bash
curl -X POST http://127.0.0.1:8000/security/authorize \
  -H "Content-Type: application/json" \
  -d '{"actor":"odoo_agent","action":"odoo.propose_change","resource":"sale.order"}'
# → {"decision":"require_approval","reason":"matched a require_approval rule"}

curl http://127.0.0.1:8000/audit/verify
# → {"valid":true,"events_checked":N}
```

## What's real vs. what's a stub

**Real:** the policy engine (fail-closed, YAML-driven RBAC), the hash-chained
audit log (tamper-evident — see `governance/audit/store.py`), the approval
lifecycle (request/pending/decide/expire, never auto-approves), and the fail-
closed behavior everywhere the design doc called for it.

**Stubbed / not yet built:** `POST /security/secrets/resolve` from the design
doc isn't implemented — it needs a real secrets backend (Vault or SOPS+age,
per the Phase 2 config design) that doesn't exist yet. Policy is a single
YAML file (`governance/security/policies/default.yaml`) with one sample role;
real roles for every agent get added here as each agent is built.

**Phase 13 addition:** `GET /approval` (bare, optional `status` filter) —
the general listing `/pending` never was. Observability's Metrics
Dashboard needs decided (approved/rejected/expired) requests too, to
compute time-to-decision, not just the still-open queue. Same
lazy-expire-before-listing behavior as `/pending`.

## Postgres (this is the tested, primary path — not SQLite)

```bash
export DATABASE_URL="postgresql://user:pass@host:5432/governance"
uvicorn main:app --reload
```

`psycopg2-binary` is in `requirements.txt`. No other code changes needed —
`governance/db.py` picks the dialect up from the connection string, and the
SQLite-only `StaticPool` setting is skipped automatically for any non-SQLite
URL (Postgres gets the normal connection pool, which is what you want for
real concurrent traffic anyway).

**Two real bugs surfaced by testing this against an actual Postgres instance,
both now fixed and covered by tests:**

1. **Missing driver.** `psycopg2-binary` wasn't in `requirements.txt` at all —
   pointing `DATABASE_URL` at Postgres would have failed immediately.
2. **Silent timestamp corruption under a non-UTC session.** The original
   columns were plain `DateTime` (Postgres `TIMESTAMP WITHOUT TIME ZONE`).
   Confirmed directly: writing `12:00:00 UTC` and reading it back under a
   Postgres session set to `America/New_York` returned `08:00:00` with no
   timezone info — a silent 4-hour shift, exactly the session's UTC offset.
   This would have corrupted every timestamp in the audit log — a serious
   problem for a log whose entire point is being a trustworthy record — on
   any Postgres instance not configured for a UTC session, and nothing
   would have signaled the corruption. Fixed by using `DateTime(timezone=True)`
   (Postgres `TIMESTAMPTZ`) on every timestamp column, which stores the
   real UTC instant regardless of session timezone. `tests/test_audit.py::
   test_stored_timestamp_survives_round_trip_as_the_same_utc_instant` is a
   permanent regression test for this — it was run against a deliberately
   reintroduced version of the bug to confirm it actually catches it, not
   just that it happens to pass.

If your Postgres is already configured with a UTC session by convention,
you'd likely never have hit this. It's fixed regardless, since relying on
every deployment remembering to configure that isn't something to bet an
audit log's integrity on.

SQLite remains available (`sqlite:///./governance.db`, the default with no
`DATABASE_URL` set) purely for a zero-install local sanity check — it isn't
the tested deployment path.

## Adding a new agent's policy

Add a block to `governance/security/policies/default.yaml` (or a new `.yaml`
file in the same directory — all of them load) following the existing
`odoo_agent` example, then `POST /security/reload` to pick it up without a
restart. If the agent's mutating actions route through Git Manager (Phase
6), its role block also needs `shell.execute: allow` alongside the `git.*`
actions — Git Manager's own branch/commit/push calls re-check
`shell.execute` for the same capability at the Shell Executor layer, so
omitting it silently denies every git action even though `git.*` itself
is allowed (a real bug caught by Phase 10's live testing, documented in
`services/agents/README.md`). **`/security/reload` only re-parses policy
YAML — it does not pick up new API routes.** Adding a genuinely new
endpoint (like Phase 10's `POST /security/verify_environment`) needs a
process restart, not just a reload; a call to a not-yet-restarted
process returns a generic `404`, easy to misread as a policy denial.
If the agent's real reads/writes touch `demo_erp` (or any target in
`secrets_registry.yaml`), its capability name also needs adding to that
target's own `allowed_capabilities` list — a *separate* allow-list from
this file's `roles:` section, enforced by Database Connector's own
`secrets.resolve` call, not by `/security/authorize` at all. Getting the
`db.read`/`db.propose_write` policy rule right here is not sufficient
on its own; a Phase 14 live test caught exactly this gap (`database_agent`
was the only entry `secrets_registry.yaml` had, from when Phase 7 wrote
it, so `accounting_agent`/`inventory_agent` got a `403` at the
credential-resolution layer even with a fully correct policy role).
Similarly, if the agent's mutating actions route through Git Manager,
it needs its own `services/execution/execution/shell_executor/allowlists/<name>.yaml`
file — a *third* independent gate from this file's `git.*`/`shell.execute`
rules, enforced by Shell Executor's own default-deny lookup. Missing
that file entirely denies with `"no command allowlist registered for
'<name>'"`, a different failure mode from the missing-`shell.execute`
bug above but the same root cause: a real capability boundary lives in
more than one file, and adding an agent means updating all of them, not
just this one.

## Phase 7 / Phase 10 / Phase 11 / Phase 12 / Phase 14 additions

- `POST /security/secrets/resolve` (Phase 7): fail-closed credential
  resolution for Database Connector, backed by `secrets_registry.yaml`
  (an env-var-indirection registry, never real credentials committed).
- `POST /security/verify_environment` (Phase 10): Testing Agent's
  structural gate — verifies a resolved execution target is a
  designated sandbox before every `testing.run_suite`, backed by the
  same indirection-registry pattern (`environment_registry.yaml`).
  Every decision is both audit-logged (same as everything else) and
  persisted to its own `test_execution_target` table, so "did we
  actually check before this run" is answerable without cross-
  referencing the general audit log.
- `code_analysis.raw_source_request` (Phase 11): no new endpoint here —
  routed through the existing `/security/authorize` +
  `/approval/request` pair, the same two-call pattern every other
  approval-gated action in this system already uses. Added as
  `require_approval` to every agent role that plausibly needs real
  function/class-body detail (`odoo_agent`, `database_agent`,
  `django_agent`, `devops_agent`, `docker_agent`, `testing_agent`) —
  `planner` deliberately excluded, since routing decisions never need
  actual source code. Also added a minimal `git_manager` role
  (`code_analysis.scan: allow`) for Phase 11's own `on_commit`
  auto-trigger — a system action attributed to the triggering service,
  not an agent capability, so it gets its own narrow role rather than
  piggybacking on `human_admin`'s blanket allow.
- `mcp.invoke` (Phase 12): added `allow` to every existing non-planner
  agent role — MCP Client is a new tool *source*, not a new trust
  boundary (the doc's own framing), so this mirrors `shell.execute`'s
  existing precedent: the individual MCP server was already
  approval-gated at registration time, this is authorize-checked
  defense-in-depth per call, not a second human approval per invocation.
  `mcp.register` and `plugin.install` themselves needed no new policy
  rule at all — both are unconditionally approval-gated in
  `services/extensibility/`'s own code, the same posture Documentation
  Engine's `classify-override` already established, not conditioned on
  an `authorize()` decision first.
- `costing_agent` / `accounting_agent` / `inventory_agent` (Phase 14):
  new roles following the same pattern as every prior batch.
  `accounting_agent` is deliberately the most restrictive of the three —
  no `db.write` at all, since `accounting.propose_entry` materializes as
  a reviewable git document (execution_bridge), never a direct ledger
  write, matching the Phase 14 doc's explicit conservatism for this one
  agent.

## Phase 15 / Phase 16 / Phase 18 additions

- `manufacturing_agent` / `sales_agent` / `project_management_agent`
  (Phase 15): new roles following the same pattern as every prior
  batch. `sales_agent` is the first role to also need `db.read_pii:
  allow` — a genuinely new action, the coarse first-layer gate for
  Database Connector's own orthogonal PII dimension
  (`services/database/README.md` has the full mechanism); the
  target-specific fine-grained gate (which capability may see which
  PII column) lives entirely in Database Connector's own
  `pii_registry.yaml`, not here.
- `code_review_agent` / `reverse_engineering_agent` / `architecture_agent`
  (Phase 16): new roles. `code_review_agent` is the first role with NO
  `require_approval` rule at all on any of its own actions — its
  output is advisory, attached to ANOTHER agent's pending approval via
  the new `POST /approval/{id}/attach_review` mechanism below, never a
  decision of its own. `reverse_engineering_agent` is the first
  capability besides `human_admin`'s wildcard to get `docs.ingest:
  allow` — no agent needed to write real documentation before this
  phase.
- **`POST /approval/{request_id}/attach_review`** (Phase 16, new): a
  second agent's structured input attached to another agent's pending
  (or already-decided) approval — additional context for the human
  approver, never a decision itself. Append-only (`ApprovalReview`
  table); never touches the target approval's own `status`/`decided_by`.
  `GET /approval/{request_id}` now returns a `reviews: []` array
  alongside the approval itself. Fails with a clean 404 only if the
  target approval doesn't exist at all — confirmed live end to end via
  Code Review Agent's own reasoning-loop test: a real diff gets fetched,
  a real assessment attaches to a real OTHER agent's pending approval,
  and that approval's own pending status is confirmed unchanged by
  fetching it back independently, not by trusting Reasoning Engine's
  own report.
- `python_agent` / `documentation_agent` / `security_agent` / `research_agent`
  (Phase 18): new roles. `security_agent` is the second role (after
  Phase 16's `code_review_agent`) with no `require_approval` rule
  anywhere in it — purely advisory, same posture. `documentation_agent`
  gets `docs.ingest: allow` too, the same grant `reverse_engineering_agent`
  already has, since an approved `docs.propose_new_doc` chains into the
  same real ingest step for a second agent.
- **`GET /audit/query` gained a `correlation_id` filter** (Phase 18,
  new) — the standard way this system already threads a single task's
  related events together, but this endpoint only ever supported
  `actor_id`/`action` until Security Agent's `security.audit_query`
  needed a real, complete trail for one specific task. Confirmed live:
  querying by a real correlation_id returns exactly the matching events,
  nothing else.

## Phase 20 addition — real restore-drill result

`deploy/backup.sh` / `deploy/restore.sh` (Phase 20, `docs/phase-20-backup-
disaster-recovery.md`) were exercised live against this environment's own
Postgres instance, not just written and described. The exact sequence run
once, using a disposable `governance_dr_drill` database:

1. Started governance against a fresh `governance_dr_drill` database.
2. Generated 5 real audit events via `POST /security/authorize`.
3. Baseline `GET /audit/verify` → `{"valid":true,"events_checked":5}`.
4. `pg_dump -Fc` (via `backup.sh`) → real 6352-byte dump file.
5. `DROP DATABASE governance_dr_drill; CREATE DATABASE governance_dr_drill;`
   — a real, deliberate destruction of all 5 rows.
6. `pg_restore --clean --if-exists --no-owner` (via `restore.sh`) from the
   dump into the now-empty database.
7. Restarted governance against the restored database and called
   `GET /audit/verify` again.

**Real result, not asserted:** step 7 returned
`{"valid":true,"events_checked":5}` — the same result as the pre-destruction
baseline. All 5 rows and the hash chain linking them survived the full
backup → destroy → restore cycle intact; `pg_restore` did not silently drop
the tail of the chain or corrupt the hash linkage. Confirmed independently
with `SELECT count(*) FROM audit_event` (`5`) before restarting the service,
not just by trusting the API response.

The disposable database was dropped again after this drill — it was never
depended on by any other phase's tests or live services, and nothing else
in this repo points at `governance_dr_drill`.

## Phase 26 addition

- `mcp_surface` (Phase 26): new role for `services/mcp-surface/`'s fixed,
  stub-auth actor — 8 `mcp_surface.*` actions, every one `allow`, every
  one still authorize()+audit_log() gated per call (same defense-in-depth
  posture as `mcp.invoke`'s own role grants since Phase 12), plus
  `task.create: allow` (Gateway's own `POST /api/v1/tasks` independently
  re-checks `task.create` for whatever actor a bearer token resolves to,
  on top of the `mcp_surface`-specific grant). Deliberately **no**
  `approval.decide`-shaped action anywhere in this role — an AI-driven
  IDE session must never be able to approve its own risky actions; this
  is the non-negotiable requirement Phase 26 exists to enforce, backed
  here structurally (no such action grant exists) in addition to
  `services/mcp-surface/` itself having no tool that could even ask for
  one.
- `research.invoke_mcp_tool` (Phase 26): added `allow` to `research_agent`'s
  role — a distinct action name from the pre-existing `mcp.invoke` grant
  (Phase 12). `loop.py`'s tool-call dispatch authorizes on this top-level
  action; extensibility's own `/mcp/invoke` separately authorizes on
  `mcp.invoke` for the same capability — two real, independent checks.

## Phase 27 addition

- `ide_client` (Phase 27): new role for `services/platform-spine`'s
  OpenAI-compatible shim's fixed, stub-auth actor — `model.generate: allow`
  and `model.list: allow`, same stub-identity posture as `mcp_surface`
  (Phase 26). This `allow` rule is deliberately NOT the real security
  gate for this phase — the actual "confidential content structurally
  barred from a lower-ceiling model" check is a separate, content-
  dependent comparison `openai_shim.py` runs against `services/assembly/`'s
  real `ceiling_for_model()` on every single request, independent of
  this role grant existing at all.

## Next

This is one piece of Phase 1's design; Phase 2 (Gateway, Task Manager,
Configuration Manager) is the next thing to build the same way — real code,
verified with real tests — once this is reviewed.
