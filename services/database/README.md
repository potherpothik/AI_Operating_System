# Phase 7 — Database Connector & Database Agent (working implementation)

Real, tested code. The most operationally sensitive phase built so far —
the first time the system gets a path, however gated, to mutate the
actual data an ERP runs on. `database_agent`'s capability declaration and
prompt template live in `services/agents/agents/database_agent/`, the
same pattern as Odoo Agent: agents are configuration over the shared
Reasoning Engine, not separate services.

## Run it

```bash
pip install -r requirements.txt
export SECURITY_LAYER_URL=http://localhost:8000   # governance must already be running
# governance's secrets registry (services/governance/governance/security/secrets_registry.yaml)
# maps target_db "demo_erp" to this env var — set it wherever governance runs, not here:
export DEMO_ERP_DATABASE_URL=postgresql://user:pass@host:5432/demo_erp
uvicorn main:app --port 8007
```

Optional, for the real migration-file-generation path:
```bash
export DJANGO_PROJECT_PATH=/path/to/a/real/django/project    # for target_platform=django
export ODOO_MODULES_PATH=/path/to/a/real/odoo/module/tree     # for target_platform=odoo
```

## Test it

```bash
pytest tests/test_query_builder.py tests/test_scoping.py tests/test_migration_adapter.py -q   # no external dependencies

SECURITY_LAYER_URL=http://localhost:8000 \
DEMO_ERP_DATABASE_URL=postgresql://user:pass@host:5432/demo_erp \
pytest tests/ -v   # full suite against real Postgres
```

41 tests, all passing against real Postgres (genuine `TIMESTAMPTZ`
columns, confirmed via direct schema inspection, under a non-UTC
session) and a real disposable target database (`demo_erp` — seeded
`sale_order`/`res_partner` tables, never any service's own operational
database or anything resembling real production data).

## Two real bugs found by live testing, not the test suite

1. **A raw database error used to crash the endpoint instead of failing
   cleanly.** The first version of `/db/dry_run` and `/db/query` only
   caught this module's own exception types — a genuine SQL error (e.g.
   a column that doesn't exist) propagated as an unhandled 500. Found by
   actually running a bad statement against real Postgres, not by
   reading the code. Fixed by catching SQLAlchemy's `DBAPIError`
   explicitly and translating it to a clean 400 — which is also the
   actual point of dry-run: a statement bad enough to fail can never
   produce a `dry_run_id` to reference, so it can never reach `/db/write`
   at all.
2. **The schema-invalid-retry path in Reasoning Engine (Phase 5) silently
   discarded tool-call context.** Database Agent's dry-run-before-write
   pattern (below) needed Reasoning Engine to inject a real query result
   into context for the model's next turn — but if THAT next response
   failed schema validation, the retry prompt was rebuilt from the
   original task description, not the one carrying the tool result,
   silently erasing the data the model was supposed to be reasoning
   from. Caught by a live model doing exactly this (a `None`
   `answer_or_proposal` triggered the retry path mid-flow). Fixed in
   `services/agents/agents/reasoning_engine/loop.py`, locked in as a
   permanent regression test in `services/agents/tests/test_database_agent.py`.

## What's real

- **Phase 13 addition:** `GET /db/query-log` (optional
  `capability`/`query_type` filters) — coarse metadata only (capability,
  target_db, query type, row count, timing), never the actual query text
  or row content. Backs Observability's Metrics Dashboard
  tool-execution-volume-by-capability category (data side); stays
  unauthenticated the same way ERP Knowledge Engine's `GET /graph`
  already is (Phase 9) — an aggregate-count view, not a data-access path.
- **`GET /db/schema/{target}` now includes real foreign-key relationships**
  alongside column names (Phase 9 addition) — `sale_order.partner_id`
  correctly reports referencing `res_partner.id`, confirmed by
  introspecting the real constraint, not inferred from naming
  conventions. Added because Phase 9's ERP Knowledge Engine needed real
  relationship data for its structured graph query mode ("what tables
  reference this one") and the original endpoint only returned columns.
  Same read-only, capability-authorized path as before — no new
  privilege.
- **Structural parameterization, not a naming convention.** `/db/query`,
  `/db/dry_run`, and `/db/write` all require a SQL template with
  `:named` placeholders and a SEPARATE params object — there is no code
  path that accepts one pre-interpolated string. SQLAlchemy's
  `text().bindparams()` sends the SQL text and parameter values to the
  driver separately, confirmed directly: a value crafted to look like a
  SQL-injection payload (`"1 OR 1=1"`) never appears in the compiled
  statement text, only as a bound parameter.
- **Dry-run is a structural precondition for writing, not advisory.** A
  write's `dry_run_id` must reference a real prior dry-run whose template
  and params hash to exactly what's being executed — confirmed live:
  drifted params between preview and execution are rejected outright,
  and a write with no dry-run at all never reaches the database.
- **A write that fails at actual execution — a case dry-run's `EXPLAIN`
  structurally can't catch (e.g. a primary-key collision on `INSERT`) —
  rolls back cleanly and reports `failed`, confirmed by checking the
  target table directly afterward, not by trusting the response.**
- **Classification-aware column scoping is enforced on real result
  data**, not just the query text: confirmed live, a `requester_ceiling`
  of `internal` genuinely strips a `confidential`-tagged column
  (`res_partner.email`) from every returned row, and `confidential`
  ceiling includes it.
- **The dry-run-before-write conversation pattern is real, live, agentic
  behavior**, not a fixed script: Database Agent's own prompt template
  drives a genuine two-turn exchange through Reasoning Engine (Phase 5)
  — `db.dry_run` first, a real impact estimate fed back into context,
  then `db.propose_write` with that real number attached — confirmed
  with a real disposable-database write landing correctly after human
  approval, verified independently by querying the target directly.
- **Governance's `secrets.resolve`** (new in this phase, added to
  `services/governance`) is a genuine fail-closed indirection: an
  unregistered target, a capability not on the allow list, or a missing
  environment variable all return a clean 403/404 rather than any
  fallback, and the resolved credential is never written to the audit
  log — confirmed by asserting the actual secret value never appears in
  any logged event.
- **Migration file generation is real, not simulated**, when configured:
  pointing `DJANGO_PROJECT_PATH`/`ODOO_MODULES_PATH` at a real directory
  produces an actual Python file, self-verified with `ast.parse` (not
  just assumed syntactically valid) before being written to disk.

## What's a stub or simplified

- **No live Django or Odoo project exists in this environment**, so
  `migration_adapter`'s file-generation path is genuinely tested against
  disposable temp directories but not against a real Django/Odoo
  install — same honesty pattern as Phase 6's untested `DockerSandbox`
  and Phase 3's untested `OllamaEmbedding`. `/db/migrate` reports
  `not_configured` cleanly rather than faking success when unconfigured.
- **Governance's `secrets_registry.yaml` is env-var indirection, not a
  real vault** — same stub posture as Phase 2's token→role file. A real
  deployment swaps the env-var lookup in `governance/security/secrets.py`
  for an actual Vault/Secrets Manager call behind the same function
  signature.
- **The dry-run/tool-call mechanism in Reasoning Engine is narrowly
  scoped to `db.read`/`db.dry_run`**, not the fully generic tool-calling
  loop the original Phase 5 doc's "tool_call_request... extension point"
  language gestured at. A deliberate, bounded choice — building the
  fully general version is appropriately deferred to whenever a second
  agent actually needs the same pattern for something else.
- **MySQL support is inherent to using SQLAlchemy** (any
  SQLAlchemy-supported `DATABASE_URL` works, `pymysql` is in
  `requirements.txt`) but genuinely verified only against Postgres in
  this environment — no MySQL instance exists here to test against.
- **Row-level classification scoping is column-only**, not per-row —
  the Phase 7 doc's future extension points note Postgres row-level
  security (RLS) as a future enforcement layer beneath this one.

## Next

Phase 8: **Planner** — with two working agents now proven (Odoo Agent,
Database Agent), this closes the gap flagged as out of scope since
Phase 2: automatic task decomposition and agent selection, instead of
`agent_capability` continuing to be handed in as a given input.
