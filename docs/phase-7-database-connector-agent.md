# Phase 7 — Data Execution Layer
### Database Connector · Database Agent

---

## 0. Priority Decision: Why This Phase Is Seventh

**Why it exists here:** Phase 6 gave agents a safe path to propose code/config changes; this phase gives an equally safe but structurally more cautious path to propose *data* changes. Database Connector and Database Agent are paired the same way Shell Executor led into Git Manager, and Reasoning Engine led into Odoo Agent — connector infrastructure alongside the first agent that exercises it. The defining addition beyond Phase 6 is a **mandatory dry-run before any write**: a git branch is fully disposable and reviewable as a diff before merge, but a database write can be irreversible the moment it executes — the preview has to happen structurally *before* execution, not as a code-review step after.

**Alternatives considered**
- *Treat DB writes like git commits — execute against a scratch copy, let a human diff it before promoting* — seriously considered, and kept as a future extension for genuinely small tables, but rejected as the default. Cloning a production-scale database per proposed write doesn't scale the way a git branch does; EXPLAIN-based impact estimation is the practical default.
- *Rely on Human Approval Layer review of proposal text alone, no dedicated dry-run step* — rejected. A human reading "update stale inventory records" cannot judge blast radius the way they can eyeball a git diff. The dry-run's row-count and impact estimate is what makes the review meaningful — the approval step alone isn't enough.
- *Fold Database Connector's responsibilities into Shell Executor, since it's ultimately another controlled-execution-against-an-external-system case* — rejected. SQL-injection defense (parameterized queries) and classification-aware column/row scoping are meaningfully different mechanisms from shell sandboxing. Conflating them risks neither being done well — the same reasoning that kept Git Manager a specialized layer above, not inside, Shell Executor.

**Trade-offs:** dry-run-first adds real latency to every write path — two round trips minimum, estimate then execute. Accepted, because execute-first-and-hope is exactly the failure mode a confidentiality-first ERP system can't afford around its own business data.

**Security implications:** this is the first phase where the system gets a path to mutate the actual business data the ERP runs on — a materially different risk category from code changes, which are reviewable, revertible, and don't touch live business state directly. Every mechanism here exists because of that distinction.

**Performance implications:** connection pooling and result-size limits matter more here than almost anywhere else, since Database Connector sits directly between agents and the databases the live ERP depends on. A runaway agent query must never be able to degrade production performance for real users.

**Future scalability:** routing DDL through the underlying platforms' own migration tooling (Django migrations, Odoo's module upgrade mechanism) rather than raw `ALTER` statements keeps agent-proposed schema changes compatible with however the engineering team already manages schema evolution, instead of creating a second, parallel, agent-only path that could drift from the real one.

**Estimated complexity:** High. The most operationally sensitive module built so far — parameterized-query enforcement, classification-aware scoping, dry-run/impact estimation, and migration-tooling integration are each nontrivial individually, and all four have to be correct together.

---

## 1. Database Connector

**Responsibilities**
- The only module permitted to open connections to or execute queries against PostgreSQL/MySQL — same chokepoint principle as Shell Executor for shell commands
- Connection pooling per database/schema; credentials resolved via `Security Layer.secrets.resolve` (Phase 1), never stored directly
- Classifies every query as read / write / DDL, with progressively stricter handling at each tier
- **Read path:** parameterized queries only — structurally, not conventionally, enforced (the API accepts a query template plus a params object, never a raw string) — with classification-aware row/column scoping
- **Write path:** every write requires a preceding dry-run/`EXPLAIN` step showing exactly what it would affect (e.g. "this UPDATE touches 40,000 rows" is a very different risk than "touches 1 row") before it can execute
- **DDL path:** schema-altering statements always require Human Approval Layer with no exceptions, and are always routed through the underlying platform's own migration tooling (Django migrations for Django-managed tables, Odoo's module upgrade mechanism for Odoo-managed tables) rather than raw `ALTER`/`CREATE`/`DROP` from an agent
- Query result size limits, so an agent can't pull an entire multi-million-row table into context
- Backup-before-write hook for high-risk operations where feasible, giving the future backup/disaster-recovery strategy a natural integration point

**Inputs:** `{query_type: read|write|ddl, sql_or_orm_call, params, target_db, target_schema, capability, requesting_agent, task_id, dry_run: bool}`

**Outputs:** read → `{rows, row_count, columns, truncated}`; write/ddl → `{affected_rows_estimate, execution_result, transaction_id}`

**APIs**

| Endpoint | Purpose |
|---|---|
| `POST /db/query` | Read path, parameterized only |
| `POST /db/dry_run` | Impact estimate for a proposed write or DDL — no execution |
| `POST /db/write` | Execute a write; requires a matching dry-run reference, and an approval reference above trivial impact |
| `POST /db/migrate` | DDL path — always routes through the platform's real migration tooling |
| `GET /db/schema/{target}` | Read-only schema introspection, feeding Vector Search's knowledge cache (Phase 3) |

**Failure handling:** fail closed on credential resolution failure — no fallback to a cached or default credential. A write submitted without a valid, matching dry-run reference is rejected outright; dry-run isn't advisory, it's a structural precondition. Any crash mid-transaction rolls back automatically, and Database Connector confirms the rollback succeeded before reporting `failed` rather than assuming it did.

**Logging:** every query, including reads, logged with `target_db`, capability, row count, and duration. Every write/DDL logs its dry-run estimate *alongside* the actual outcome, so a reviewer can later compare what was predicted against what happened.

**Security:** parameterized queries are structurally enforced, mirroring how Prompt Builder separates trusted template from untrusted content. Classification-aware scoping is enforced server-side, the same pattern as Vector Search's classification filter in Phase 3. DDL-without-approval cannot be granted to any capability regardless of how it's declared — a hard rule in Security Layer's policy schema, not a convention. Connector credentials are scoped to least privilege at the database-user level, so a read-only agent's credential literally lacks write grants — defense in depth below the application layer.

**Future extension points:** read replicas to isolate agent read traffic from production OLTP load; Postgres row-level security (RLS) as an enforcement layer beneath Database Connector's own scoping; query-cost estimation and circuit-breaking for expensive analytical queries.

---

## 2. Database Agent

**Responsibilities**
- Capability set mirrors Odoo Agent's conservative posture, adapted for data: read (classification-scoped, via Database Connector), propose-write (produces a dry-run impact estimate plus a plain-language explanation, never executes), propose-migration (DDL, always routed to Database Connector's approval-gated migrate path)
- Knows when to refuse: any request that would require an unparameterized query (should never reach Database Connector at all given its structural enforcement, but Database Agent is instructed to refuse to even attempt constructing one — defense in depth at the reasoning layer too); requests to skip dry-run; requests outside its declared database/schema scope
- Knows when to delegate: schema-design questions that are really architecture decisions go to Architecture Agent (not yet built); Odoo-specific data questions where the real answer lives in Odoo business logic rather than raw SQL go back to Odoo Agent — Database Agent's lane is DB mechanics, not business meaning
- Produces the standard structured output from Prompt Builder's schema, extended with `impact_estimate` from the mandatory dry-run
- Its prompt template frames parameterized-query-only reasoning (the model is never even prompted to produce raw interpolated SQL), states the dry-run-before-write requirement explicitly, and states its scope boundary relative to Odoo Agent

**Capability declaration**
```
capability: database_agent
allowed_actions:   [db.read, db.dry_run, db.propose_write, db.propose_migration]
forbidden_actions: [db.write_direct, db.ddl_direct, *]
requires_approval: [db.propose_write (above trivial impact), db.propose_migration (always)]
classification_ceiling: internal
```

**Inputs:** task from Task Manager routed to `agent_capability = "database_agent"`

**Outputs:** `{reasoning, answer_or_proposal, impact_estimate, confidence, provenance[], risk_classification, delegate_to?}`

**APIs:** none of its own — same pattern as Odoo Agent, configuration over the shared Reasoning Engine.

**Failure handling:** if a dry-run comes back flagged high-risk by its own numbers (affects a large share of a table, touches a column with no rollback path), the agent's template requires it to surface that explicitly and set `risk_classification` accordingly — the model isn't trusted to self-moderate without an explicit instruction to escalate on that signal.

**Logging:** agent-level outcome logged alongside Reasoning Engine's trace and Database Connector's dry-run/execution record — three linked records for the same action.

**Security:** `db.propose_write` and `db.propose_migration` are the only actions with real-world effect, and only after Database Connector's own independent dry-run and approval gate — proposing is never sufficient to execute, mirroring Odoo Agent's Phase 5 posture but with an extra structural gate that code changes don't need in the same way, since a git diff already *is* an impact preview.

**Future extension points:** learned risk calibration, comparing past impact estimates against actual outcomes to improve future accuracy; direct integration with Django's migration framework and Odoo's module upgrade mechanism, so `propose_migration` produces a real migration file in the right framework instead of generic DDL text.

---

## 3. How the Two Interact

```
Database Agent (Reasoning Engine, Phase 5): agent output = db.propose_write
        │
        ▼
Database Connector.dry_run(sql_template, params, target_db)
        ├── parameterized query only — no raw SQL ever accepted
        ├── classification-aware scoping check                                [Phase 1]
        └── → impact_estimate (rows affected, columns touched)
        │
        ▼
Database Agent: attaches impact_estimate to its output, sets risk_classification
        │
        ▼
Human Approval Layer.request(proposal + impact_estimate)                        [Phase 1]
        │  (human approves — reviewing an actual number, not just prose)
        ▼
Reasoning Engine.resume(...)
        │
        ▼
Database Connector.write(sql_template, params, dry_run_ref)
        ├── verifies dry_run_ref matches this exact write — no drift between preview and execution
        ├── wraps in transaction, executes, confirms rollback-on-failure if needed
        └── Audit Logger: dry-run estimate + actual outcome, side by side                [Phase 1]
```

---

## 4. Minimal Data Model for This Phase

```sql
db_query_log (
  id, task_id, capability, target_db, target_schema, query_type,
  query_template_hash, row_count, duration_ms, ts
)

db_dry_run (
  id, task_id, query_template_hash, params_hash, estimated_rows_affected,
  columns_touched[], created_at
)

db_write (
  id, task_id, dry_run_id, transaction_id, status,
  actual_rows_affected, executed_at, rolled_back
)

db_migration_request (
  id, task_id, target_platform,        -- 'django' | 'odoo'
  migration_ref, requires_approval, approved_by, applied_at
)
```

---

## 5. Folder Structure for This Phase

```
data/
├── database_connector/
│   ├── api.py
│   ├── pool.py                    # connection pooling, credential resolution via Security Layer
│   ├── query_builder.py            # parameterized-only query construction
│   ├── scoping.py                   # classification-aware row/column filtering
│   ├── dry_run.py                    # EXPLAIN / impact estimation
│   ├── migration_adapter/             # django.py / odoo.py — routes DDL through real tooling
│   └── store.py
└── database_agent/
    ├── capability.yaml
    └── template.md
```

---

## 6. Explicitly Out of Scope for This Phase

No MCP Client, no Plugin System — future extensibility phases. No direct DDL execution path outside the underlying platforms' own migration tooling, by design, not a gap. Branch-and-diff-style database change review (full scratch-copy comparison) is noted as a future extension, not built now.

---

## Next

Phase 8: **Planner** — with two working agents now proven (Odoo Agent, Database Agent), this is the point to close the gap flagged as out of scope since Phase 2: automatic task decomposition and agent selection, instead of `agent_capability` continuing to be handed in as a given input.
