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

41 tests, all passing (grown from the original 11 across every phase
since — secrets resolution, environment verification, and the Phase 13
general approval listing are the most recent additions): default-deny on
unknown roles, allow/deny/require_approval routing, every decision
logged, the audit hash chain validating correctly *and* correctly
detecting a tampered row, and the full approval request → pending →
decide lifecycle including rejection and expiry.

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

## Next

This is one piece of Phase 1's design; Phase 2 (Gateway, Task Manager,
Configuration Manager) is the next thing to build the same way — real code,
verified with real tests — once this is reviewed.
