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

11 tests, all passing: default-deny on unknown roles, allow/deny/require_approval
routing, every decision logged, the audit hash chain validating correctly *and*
correctly detecting a tampered row, and the full approval request → pending →
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
restart.

## Next

This is one piece of Phase 1's design; Phase 2 (Gateway, Task Manager,
Configuration Manager) is the next thing to build the same way — real code,
verified with real tests — once this is reviewed.
