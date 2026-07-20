# AI Operating System

A private, offline-first AI orchestration layer for a large engineering ERP
(Odoo 19 + Django), coordinating specialized agents instead of one giant
model. Governance-first: nothing executes without passing through Security
Layer, and every mutating action is logged and approval-gated before it
touches anything real.

Designed and built one subsystem at a time — see [`docs/`](docs/) for the
full phase-by-phase architecture (why each decision was made, alternatives
considered, trade-offs, security implications) before diving into code.
**AI agents:** start with [`docs/README.md`](docs/README.md) for the doc index
and mandatory read-before-code checklist.
Long-term picture (ERP Brain + Coding Brain on one kernel, Model Router
gap, OpenCode/Claude Code gateway): [`docs/architecture-vision.md`](docs/architecture-vision.md).

## Status

| Phase | Subsystem | Design doc | Code |
|---|---|---|---|
| 1 | Security Layer, Audit Logger, Human Approval Layer | [`docs/phase-1-governance-layer.md`](docs/phase-1-governance-layer.md) | [`services/governance/`](services/governance/) — 47 tests |
| 2 | Configuration Manager, Gateway, Task Manager | [`docs/phase-2-gateway-task-manager-config.md`](docs/phase-2-gateway-task-manager-config.md) | [`services/platform-spine/`](services/platform-spine/) — 23 tests |
| 3 | Memory Manager, Vector Search | [`docs/phase-3-memory-vector-search.md`](docs/phase-3-memory-vector-search.md) | [`services/knowledge/`](services/knowledge/) — 22 tests |
| 4 | Context Builder, Prompt Builder | [`docs/phase-4-context-prompt-builder.md`](docs/phase-4-context-prompt-builder.md) | [`services/assembly/`](services/assembly/) — 26 tests |
| 5 | Reasoning Engine, Odoo Agent | [`docs/phase-5-odoo-agent-reasoning-engine.md`](docs/phase-5-odoo-agent-reasoning-engine.md) | [`services/agents/`](services/agents/) — 27 tests |
| 6 | Shell Executor, Git Manager | [`docs/phase-6-shell-git-manager.md`](docs/phase-6-shell-git-manager.md) | [`services/execution/`](services/execution/) — 72 tests |
| 7 | Database Connector, Database Agent | [`docs/phase-7-database-connector-agent.md`](docs/phase-7-database-connector-agent.md) | [`services/database/`](services/database/) — 54 tests (Database Agent itself lives in `services/agents/agents/database_agent/`) |
| 8 | Planner, Capability Registry | [`docs/phase-8-planner-capability-registry.md`](docs/phase-8-planner-capability-registry.md) | [`services/planning/`](services/planning/) — 27 tests (Planner itself lives in `services/agents/agents/planner/`) |
| 9 | Documentation Engine, ERP Knowledge Engine | [`docs/phase-9-documentation-erp-knowledge-engine.md`](docs/phase-9-documentation-erp-knowledge-engine.md) | [`services/knowledge_pipelines/`](services/knowledge_pipelines/) — 27 tests |
| 10 | Django, DevOps, Docker, Testing Agents | [`docs/phase-10-django-devops-docker-testing-agents.md`](docs/phase-10-django-devops-docker-testing-agents.md) | [`services/agents/`](services/agents/) — 38 tests (all four agents live in `services/agents/agents/{django_agent,devops_agent,docker_agent,testing_agent}/`) |
| 11 | Code Analysis Engine | [`docs/phase-11-code-analysis-engine.md`](docs/phase-11-code-analysis-engine.md) | [`services/knowledge_pipelines/`](services/knowledge_pipelines/) — 53 tests (Code Analysis Engine itself lives in `services/knowledge_pipelines/knowledge_pipelines/code_analysis_engine/`) |
| 12 | MCP Client, Plugin System | [`docs/phases-12-21-remaining-subsystems.md`](docs/phases-12-21-remaining-subsystems.md) | [`services/extensibility/`](services/extensibility/) — 25 tests |
| 13 | Metrics Dashboard, Health Monitor | [`docs/phase-13-metrics-health.md`](docs/phase-13-metrics-health.md) | [`services/observability/`](services/observability/) — 19 tests |
| 14 | Costing, Accounting, Inventory Agents | [`docs/phases-12-21-remaining-subsystems.md`](docs/phases-12-21-remaining-subsystems.md) | [`services/agents/`](services/agents/) — 50 tests (all three agents live in `services/agents/agents/{costing_agent,accounting_agent,inventory_agent}/`) |
| 15 | Manufacturing, Sales, Project Management Agents | [`docs/phase-15-operations-agents.md`](docs/phase-15-operations-agents.md) | [`services/agents/`](services/agents/) — 61 tests (all three agents live in `services/agents/agents/{manufacturing_agent,sales_agent,project_management_agent}/`; also extends `services/database/` with a new PII classification dimension and `services/platform-spine/` with a task-events endpoint) |
| 16 | Code Review, Reverse Engineering, Architecture Agents | [`docs/phase-16-code-quality-agents.md`](docs/phase-16-code-quality-agents.md) | [`services/agents/`](services/agents/) — 69 tests (all three agents live in `services/agents/agents/{code_review_agent,reverse_engineering_agent,architecture_agent}/`; also extends `services/governance/` with an approval-review attachment mechanism) |
| 17 | Calculation, Cutlist Optimization, AutoCAD Agents | [`docs/phase-17-engineering-calculation-agents.md`](docs/phase-17-engineering-calculation-agents.md) | [`services/agents/`](services/agents/) — 78 tests (all three agents live in `services/agents/agents/{calculation_agent,cutlist_optimization_agent,autocad_agent}/`; also adds real deterministic scripts under `services/execution/` and a formula-by-name gap-fill on `services/knowledge_pipelines/`) |
| 18 | Python, Documentation, Security, Research Agents | [`docs/phase-18-cross-cutting-agents.md`](docs/phase-18-cross-cutting-agents.md) | [`services/agents/`](services/agents/) — 87 tests (all four agents live in `services/agents/agents/{python_agent,documentation_agent,security_agent,research_agent}/`; also adds a `correlation_id` filter to `services/governance/`'s audit query) |
| 19 | Deployment Architecture, Docker Deployment | [`docs/phase-19-deployment-docker.md`](docs/phase-19-deployment-docker.md) | real `Dockerfile`s (all eleven services) + [`docker-compose.yml`](docker-compose.yml) — written to the real interface, unbuilt/unverified (no Docker daemon in this environment) |
| 20 | Backup Strategy, Disaster Recovery | [`docs/phase-20-backup-disaster-recovery.md`](docs/phase-20-backup-disaster-recovery.md) | [`deploy/backup.sh`](deploy/backup.sh), [`deploy/restore.sh`](deploy/restore.sh) — real, live restore drill run against a disposable database; result in [`services/governance/README.md`](services/governance/README.md#phase-20-addition--real-restore-drill-result) |
| 21 | Consolidated reference | [`docs/phases-12-21-remaining-subsystems.md`](docs/phases-12-21-remaining-subsystems.md) | not yet built |
| 22 | Coding Agent Gateway (OpenCode, Claude Code) | [`docs/phase-22-external-coding-agents.md`](docs/phase-22-external-coding-agents.md) | not yet built |
| 24 | Control UI (Web Shell — chat, approvals, ops, views) | [`docs/phase-24-control-ui.md`](docs/phase-24-control-ui.md) | not yet built |

Eleven services are real, tested code today, now hosting Phases 1–18
(1–11 as their own dedicated design docs, 12–14 from the consolidated
Phases 12–21 doc, 15/16/17/18 each from their own dedicated design doc —
written separately because each phase's core mechanism (PII scoping;
approval-review attachment; real sandboxed deterministic execution; a
real audit-trail tool call) is a
material change to an already-built service, not just agent
configuration). Phase 19 adds real deployment artifacts written to the
interface but unverified (no Docker daemon here). Phase 20 adds two real
shell scripts, live-drilled against this environment's own Postgres
instance — a genuinely different, stronger honesty tier than Phase 19,
since `pg_dump`/`pg_restore` are actually available here. Everything past
Phase 20 is fully designed but not yet implemented. Vision and ElizaOS
study notes:
[`docs/architecture-vision.md`](docs/architecture-vision.md),
[`docs/elizaos-borrowed-ideas.md`](docs/elizaos-borrowed-ideas.md). Doc
index and mandatory read-before-code checklist: [`docs/README.md`](docs/README.md).

## Running what exists

Each service is independently runnable and has its own README with real
run/test instructions. Dependency order: `governance` has none;
`platform-spine` and `knowledge` both call `governance`; `assembly` calls
all three of the others; `execution` and `database` each call only
`governance` directly; `planning` calls `governance`, `agents` (to sync
its capability roster and run Planner), and `platform-spine` (to create
real subtasks); `knowledge_pipelines` calls `governance`, `knowledge`
(where real content actually lands), and `database` (ERP schema sync);
`agents` calls all of the above plus a local Ollama instance, and calls
back into `execution` (an approved code change), `database` (an approved
data write or migration), `knowledge_pipelines` (an approved formula
change, Phase 14), and `planning` (to fetch the live capability roster
Planner reasons over) — closing all three loops end to end.
`extensibility` (Phase 12) calls `governance`, `assembly` (to register a
plugin's template), and `agents` (to trigger a hot capability reload
after a plugin is approved) — the `agents` service itself needs to be
told the same `PLUGIN_CAPABILITIES_DIR` for that reload to actually
surface anything. `observability` (Phase 13) calls every other service
with a plain GET — never a write — to aggregate liveness and metrics;
it's the one service every other service doesn't need to know exists.

```bash
# terminal 1 — DEMO_ERP_DATABASE_URL is only needed once you're using Phase 7;
# governance's secrets_registry.yaml resolves it on this process's behalf
cd services/governance && pip install -r requirements.txt
DEMO_ERP_DATABASE_URL=postgresql://user:pass@host:5432/demo_erp uvicorn main:app --port 8000

# terminal 2
cd services/platform-spine && pip install -r requirements.txt
SECURITY_LAYER_URL=http://localhost:8000 uvicorn main:app --port 8002

# terminal 3
cd services/knowledge && pip install -r requirements.txt
SECURITY_LAYER_URL=http://localhost:8000 uvicorn main:app --port 8003

# terminal 4
cd services/assembly && pip install -r requirements.txt
SECURITY_LAYER_URL=http://localhost:8000 PLATFORM_URL=http://localhost:8002 KNOWLEDGE_URL=http://localhost:8003 \
uvicorn main:app --port 8004

# terminal 5 — CODE_ANALYSIS_URL is only needed once you're using Phase 11's
# on_commit auto-trigger; without it, commits still succeed, the trigger
# is just skipped
cd services/execution && pip install -r requirements.txt
SECURITY_LAYER_URL=http://localhost:8000 SANDBOX_ROOT=/tmp/ai_os_sandbox CODE_ANALYSIS_URL=http://localhost:8009 \
uvicorn main:app --port 8006

# terminal 6 — governance's secrets_registry.yaml maps target_db "demo_erp"
# to this env var (set it wherever governance itself runs, not here)
cd services/database && pip install -r requirements.txt
SECURITY_LAYER_URL=http://localhost:8000 \
uvicorn main:app --port 8007

# terminal 7 — needs Ollama running locally with a model pulled.
# KNOWLEDGE_PIPELINES_URL closes Phase 14's costing.propose_formula_change
# loop; PLUGIN_CAPABILITIES_DIR must match terminal 10's own env var (Phase 12)
cd services/agents && pip install -r requirements.txt
SECURITY_LAYER_URL=http://localhost:8000 PLATFORM_URL=http://localhost:8002 \
KNOWLEDGE_URL=http://localhost:8003 ASSEMBLY_URL=http://localhost:8004 \
EXECUTION_URL=http://localhost:8006 PROPOSAL_REPO_PATH=/tmp/ai_os_sandbox/your-real-repo-clone \
DATABASE_CONNECTOR_URL=http://localhost:8007 CAPABILITY_REGISTRY_URL=http://localhost:8008 \
KNOWLEDGE_PIPELINES_URL=http://localhost:8009 PLUGIN_CAPABILITIES_DIR=/tmp/ai_os_plugins \
uvicorn main:app --port 8005

# terminal 8
cd services/planning && pip install -r requirements.txt
SECURITY_LAYER_URL=http://localhost:8000 AGENTS_URL=http://localhost:8005 PLATFORM_URL=http://localhost:8002 \
uvicorn main:app --port 8008
# once agents is up: curl -X POST localhost:8008/capabilities/sync

# terminal 9 — ASSEMBLY_URL is Phase 11's raw-source-request model-isolation
# re-check (Code Analysis Engine's raw_source_gate.py)
cd services/knowledge_pipelines && pip install -r requirements.txt
SECURITY_LAYER_URL=http://localhost:8000 KNOWLEDGE_URL=http://localhost:8003 \
DATABASE_CONNECTOR_URL=http://localhost:8007 ASSEMBLY_URL=http://localhost:8004 \
uvicorn main:app --port 8009

# terminal 10 — Phase 12: PLUGIN_CAPABILITIES_DIR must match terminal 7's
# own env var of the same name
cd services/extensibility && pip install -r requirements.txt
SECURITY_LAYER_URL=http://localhost:8000 ASSEMBLY_URL=http://localhost:8004 \
AGENTS_URL=http://localhost:8005 PLUGIN_CAPABILITIES_DIR=/tmp/ai_os_plugins \
uvicorn main:app --port 8010

# terminal 11 — Phase 13: every URL below is optional in the sense that
# an unreachable one just shows up as "down" or "partial" in the
# response, never a crash; set all of them for a genuinely useful view
cd services/observability && pip install -r requirements.txt
GOVERNANCE_URL=http://localhost:8000 PLATFORM_URL=http://localhost:8002 \
KNOWLEDGE_URL=http://localhost:8003 ASSEMBLY_URL=http://localhost:8004 \
AGENTS_URL=http://localhost:8005 EXECUTION_URL=http://localhost:8006 \
DATABASE_CONNECTOR_URL=http://localhost:8007 PLANNING_URL=http://localhost:8008 \
KNOWLEDGE_PIPELINES_URL=http://localhost:8009 EXTENSIBILITY_URL=http://localhost:8010 \
uvicorn main:app --port 8011
```

All default to SQLite with zero setup. Point `DATABASE_URL` at Postgres
for the real deployment target — each service's README has the exact
connection string format and what's been verified against it (including
`knowledge`'s use of real pgvector, not a stand-in).

## Deploying with Docker Compose (Phase 19)

```bash
cp .env.example .env    # fill in real POSTGRES_PASSWORD / DEMO_ERP_DATABASE_URL / GATEWAY_TOKEN
docker compose build
docker compose up -d
```

Real, reviewed `Dockerfile`s for all eleven services plus a real
`docker-compose.yml` — one Postgres instance with one logical database
per service (`deploy/postgres-init/01-create-databases.sql`), the same
`pgvector/pgvector:pg16` image `knowledge`'s real Vector Search needs,
four networks matching Phase 6's own "no network by default" sandboxing
principle applied at the deployment layer (`public`: Gateway only;
`internal`: every service; `data-net`: Postgres; `model-net`: Ollama,
reached only by `agents`). Design and full honesty notes:
[`docs/phase-19-deployment-docker.md`](docs/phase-19-deployment-docker.md).

**Read before relying on this**: no Docker daemon exists in this
development environment (confirmed directly, the same constraint
`DockerSandbox` has carried since Phase 6) — every file here is written
to the real interface and cross-checked line-by-line against what each
service's own README already documents needing, but genuinely unbuilt
and unverified against a live `docker compose up`. `depends_on` alone
orders container start, not readiness — no `healthcheck:` blocks exist
yet, a real, named follow-up. `PROPOSAL_REPO_PATH`'s real git working
directory isn't something Compose creates for you; a one-time real
`git clone` into the `sandbox-data` volume is a genuine deployment-time
step.

## Honesty notes worth reading before relying on this

- **`knowledge`'s embedding model**: no route to HuggingFace Hub or a live
  Ollama instance existed while building this, so semantic search currently
  runs on a local, deterministic, lexical-overlap embedding — not a true
  semantic one. Swappable via one environment variable. Full detail in
  `services/knowledge/README.md`.
- **`assembly`'s token budgeting** is word-count based, not exact token
  counting, for the same reason — a real tokenizer needs files this
  sandbox can't download. Swappable in `budget.py`.
- **`platform-spine`'s auth** is a stub token→role file, explicitly standing
  in for real SSO/LDAP.
- **`agents`' model routing targets whatever's actually pulled in Ollama.**
  The design names `qwen-coder`/`deepseek-coder`; verified here against
  `qwen3.5:4b`, applied via `platform-spine`'s config override mechanism
  rather than editing Phase 2's shipped defaults. Thinking-capable models
  need `think: false` passed to Ollama or they can burn their entire
  output budget on invisible chain-of-thought and never answer — a real
  bug caught by reading a raw API response, not by any schema check. Full
  detail in `services/agents/README.md`.
- **`execution`'s sandbox runs on a subprocess fallback, not real Docker
  containers.** Docker isn't installed in this environment (confirmed: no
  `docker` binary at all). `DockerSandbox` is written to the real `docker
  run` contract but never actually run here; `SubprocessSandbox` is what's
  genuinely tested — real timeout/resource limits and working-directory
  confinement, but not real filesystem or network isolation (the command
  allowlist is the actual defense there). Also worth knowing: an earlier
  version set a process-count resource limit that broke `git push`
  entirely, because that particular limit is scoped per-user system-wide,
  not per-command — found by actually pushing to a repo, not by the test
  suite's assertions alone. Full detail in `services/execution/README.md`.
- **`database`'s migration file generation has no live Django or Odoo
  project to target in this environment** — `/db/migrate` reports
  `not_configured` cleanly rather than faking success unless
  `DJANGO_PROJECT_PATH`/`ODOO_MODULES_PATH` point at a real directory.
  Structural SQL-injection defense and the mandatory dry-run-before-write
  gate are both genuinely verified against a real disposable Postgres
  database, though — including a write that passes dry-run's `EXPLAIN`
  but fails at actual execution (a primary-key collision), confirmed to
  roll back cleanly. Full detail in `services/database/README.md`.
- **`planning`'s Planner reasons at a fixed local-model classification
  ceiling, not a genuine per-human clearance level** — the Phase 8 doc
  calls for planning at "the requesting human's own classification
  level," but this system has no per-human identity/clearance concept
  yet (Phase 2's auth is a stub token→role file). Two real bugs worth
  knowing about if you're extending Planner: the shared 6-field output
  schema's `delegate_to` and `risk_classification` fields don't mean the
  same thing for a routing-only capability as they do for an executing
  one — a live model reasonably applied the generic "hand this off" and
  "rate your own risk" instructions to Planner too, which would silently
  discard a real task_graph or route every plan through human approval
  before any subtask could run. Fixed with structural overrides in
  Reasoning Engine, not just prompt instructions. Full detail in
  `services/planning/README.md`.
- **`knowledge_pipelines`' document parsers are genuinely real** (PyPI
  access worked in this environment, unlike Phase 3's HuggingFace
  constraint) — real PDF/DOCX extraction, confirmed by generating actual
  files with real text and parsing them back, not blank pages or mocks.
  What's simplified: "watching" a source is poll-triggered via an
  endpoint, not a continuously-running background daemon (the first
  genuinely continuous process the Phase 9 doc anticipates, deliberately
  not built as one), and ERP Knowledge Engine syncs against the same
  seeded Postgres `demo_erp` database every phase since 7 has used —
  real relational data with a real foreign key, but not an actual Odoo
  instance, so there's no real module-manifest concept to introspect.
  Full detail in `services/knowledge_pipelines/README.md`.
- **Phase 10's four new agents** (Django, DevOps, Docker, Testing) needed
  no new services and almost no new Reasoning Engine code — `propose_*`
  actions reuse Phase 6's and Phase 7's existing bridges unchanged, and
  Planner routes to all four with zero Planner code changes (confirmed
  live: a "explain the CI/CD pipeline" question routed to `devops_agent`,
  a "report test coverage" question routed to `testing_agent`, after a
  plain `POST /capabilities/sync`). The one genuinely new mechanism —
  Testing Agent's `testing.run_suite` — can only run against an
  execution target Security Layer has structurally verified as a
  sandbox, checked fresh before every single run; `docker.inspect` and
  `testing.run_suite` were verified against `git`/real disposable repos
  rather than actual `docker`/`pytest` binaries, since neither is
  installed or on Shell Executor's minimal safe-env `PATH` in this
  environment. Full detail in `services/agents/README.md`.
- **Phase 11's Code Analysis Engine is real static analysis, not a
  stub** — Python's own `ast` module (no external dependency needed)
  extracts genuine signatures, docstrings, and an intra-file call graph,
  confirmed end to end live: a real `git commit` through Phase 6's Git
  Manager auto-triggers a real incremental scan, and the resulting
  structural content is independently queryable back out of Vector
  Search. The two-tier confidentiality split is the actual security
  design here: raw function/class bodies are never persisted anywhere
  in this service's own database, only read live from disk on an
  approval-gated request that re-verifies the requesting model is
  local-only *at release time*, not just when the request was filed —
  confirmed live, including refusing release to an approved-but-external
  target model. What's scoped down for this first version: call-graph
  resolution is intra-file only (cross-file calls aren't tracked, named
  explicitly in the design doc as a tractability trade-off), and
  JavaScript/TypeScript/Odoo-XML parsing are named extension points that
  raise a clean, explicit "not implemented" rather than a silent
  no-op. One real bug this phase caught along the way: `assembly`'s new
  `GET /context/model-ceiling` endpoint was originally unreachable due
  to FastAPI route-registration order — a literal path registered after
  a path-parameter route that happened to match anything, caught only
  by an actual HTTP call, not a direct function-call test. Full detail
  in `services/knowledge_pipelines/README.md`.
- **Phase 12's MCP Client speaks a deliberately simplified REST
  contract, not full MCP JSON-RPC 2.0** — the same "real but reduced,
  honestly labeled" posture as Phase 3's `HashingEmbedding` and Phase
  6's `SubprocessSandbox`. What's genuinely real and live-tested: the
  register → approve → activate → invoke lifecycle against a real local
  stub HTTP server (a genuine `http.server.HTTPServer`, not a mocked
  `httpx` call), an unreachable server failing closed rather than
  fabricating a result, and a result outside a server's declared schema
  being rejected. Plugin System's claim — a new agent addable "without
  modifying core code" — is proven live, not just architecturally: an
  approved plugin's `capability.yaml` lands on disk and a running
  `agents` service's own `GET /capabilities` shows the new capability
  moments later, after one small, real change to
  `capability_registry.py` (a second, configurable directory it also
  globs) rather than any change to how loading itself works. Full
  detail in `services/extensibility/README.md`.
- **Phase 14's three business agents (Costing, Accounting, Inventory)
  needed almost no new Reasoning Engine code** — Inventory Agent reuses
  Database Agent's exact dry-run-then-write path unchanged, Accounting
  Agent reuses Odoo Agent's exact git-proposal path unchanged (never a
  direct ledger write, matching this agent's deliberate conservatism),
  and the one genuinely new bridge (Costing Agent's formula-change path)
  is a ~15-line wrapper around Phase 9's already-existing formula
  registration. Planner routes to all three with zero Planner code
  changes, confirmed live the same way as Phase 10. Two real,
  independent permission-boundary gaps were caught by live testing here
  — a stale `secrets_registry.yaml` allow-list, and a missing Shell
  Executor allowlist file for `accounting_agent` — both are now fixed
  and covered by regression tests, and both are worth reading about if
  you're adding the *next* agent: a capability boundary in this system
  lives in more than one file, and governance's own `roles:` policy
  being correct is necessary but not sufficient. Full detail in
  `services/agents/README.md` and `services/governance/README.md`.
- **Phase 15's three operations agents pushed bridge reuse to its
  limit — all four `propose_*` actions across all three agents reuse
  `execution_bridge.materialize_propose_change()` completely
  unchanged**, and Manufacturing Agent's `flag_constraint` reuses the
  exact `db.read` tool call every prior data-reading agent already
  uses. The one genuinely new mechanism (`task_bridge.py`, for Project
  Management Agent's `task.read`) closes a real gap in Phase 2:
  `task_manager/store.py`'s `task_events()` had existed since that
  phase but was never reachable over HTTP until this phase added it.
  Sales Agent's `explain_status` is the first capability in this system
  to need a PII dimension genuinely separate from
  public/internal/confidential — and its own first live test caught a
  real design bug: the initial PII gate was layered *on top of* the
  classification ceiling rather than being truly independent, which
  meant Sales Agent (deliberately kept at a low `internal` ceiling)
  could never see an explicitly-authorized, explicitly-requested field
  no matter what the PII registry said. Fixed by making the two gates
  genuinely orthogonal — full detail, including the fix, in
  `services/agents/README.md` and `services/database/README.md`.
- **Phase 16's three code-quality agents are the Coding Brain's first
  real batch — a deliberate pivot after five straight ERP-brain phases.**
  Architecture Agent needed zero new mechanism at all: `database_agent`'s
  own template has said `delegate_to "architecture_agent" if you
  recognize one` since Phase 7, written when Architecture Agent didn't
  exist yet, so building it now makes that delegation resolve to
  something real for the first time. Reverse Engineering Agent's
  approved draft reuses the same git-proposal path for its commit half,
  then chains into a new bridge that ingests that SAME file into
  Documentation Engine's already-existing formula/doc registration path
  — inference becomes record, no second write mechanism invented. Code
  Review Agent needed one genuinely new governance mechanism: a second
  agent's structured assessment attaching to ANOTHER agent's pending
  approval as additive context, never a vote — its own two real tool
  calls (a real `git diff`, a real call-graph lookup) surfaced two
  live bugs in the same session: caller data came back as raw internal
  ids instead of names (fixed by switching to the endpoint that already
  resolves them), and a bare branch name diffed against the working tree
  instead of `main` (fixed on the caller's side, not the read-only
  endpoint itself). Full detail in `services/agents/README.md` and
  `services/governance/README.md`.
- **Phase 17's three engineering agents share one integrity principle:
  none of them let the model assert a numeric or layout result from its
  own generation.** Every real computation routes through an actual
  deterministic script (`eval_formula.py`, `cutlist_solver.py`,
  `dxf_parse.py`) under a new `services/execution/execution/shell_executor/scripts/`
  directory, invoked via the exact same sandboxed-subprocess path every
  other allowlisted command already uses — the model never computes
  arithmetic or a bin-packing layout itself. `eval_formula.py`'s
  restricted `ast` walker is a real security boundary, confirmed live
  with an actual code-injection attempt (`__import__('os').system(...)`)
  structurally rejected before it ever reaches a function call — never
  Python's own `eval()`. Two real bugs surfaced live in the same
  session, neither in the new scripts themselves: a literal JSON example
  in Calculation Agent's own prompt template collided with Prompt
  Builder's `str.format()`-based rendering (a `{"base_cost": 420}` in
  prose reads as a format placeholder, not an example — fixed by
  escaping the braces), and a genuine gap in ERP Knowledge Engine
  (Phase 9/14): a formula could only ever be looked up by internal id,
  never by the real name a model could plausibly know, closed with
  `GET /erp-knowledge/formula/by-name/{name}` — the underlying store
  function had existed since Phase 14, just never reachable over HTTP.
  Full detail in `services/agents/README.md`, `services/execution/README.md`,
  and `services/knowledge_pipelines/README.md`.
- **Phase 18's four cross-cutting agents were mostly config, exactly as
  `CLAUDE.md` predicted before any of them were built** — Python Agent
  and Research Agent needed zero new mechanism at all, and Documentation
  Agent's `docs.propose_new_doc` reuses Phase 16's `reverse_eng_bridge.py`
  chained docs-ingest step completely unchanged for a SECOND agent, the
  first live confirmation that bridge generalizes past the one agent it
  was written for. Security Agent needed the one genuinely new piece: a
  real, non-terminal `security.audit_query` tool call against
  governance's actual Audit Logger (Phase 1) — confirmed live with two
  real audit events under a known `correlation_id`, both showing up
  verbatim in the model's next-turn prompt. That tool call surfaced one
  small, real gap: `GET /audit/query` only ever supported `actor_id`/
  `action` filters, never `correlation_id` — the standard way this
  system already threads a task's related events together — closed with
  one new optional filter on the existing endpoint. The first phase
  since Phase 12 where every test passed on its first live run, worth
  noting plainly rather than manufacturing a bug to report for symmetry.
  Full detail in `services/agents/README.md` and
  `services/governance/README.md`.
- **Phase 19 is a different kind of deliverable than every phase before
  it — deployment infrastructure, not application code, and it says so
  plainly rather than pretending otherwise.** Real `Dockerfile`s for all
  eleven services and a real `docker-compose.yml`, adapted from the
  master roadmap's own illustrative skeleton (which named containers at
  a finer granularity than what actually got built — three separate
  governance containers where the real build made one, for instance) to
  the real, current module boundaries. Every environment variable in the
  compose file was cross-checked directly against what each service's
  own README already documents reading, not re-derived from memory. What
  it genuinely is not: built or run against a live Docker daemon — none
  exists in this environment, the same constraint `DockerSandbox` has
  carried since Phase 6, now named for a whole phase instead of one
  fallback class. Full detail, including a real, named gap
  (`depends_on` without healthchecks doesn't wait for real readiness),
  in `docs/phase-19-deployment-docker.md`.
- **Phase 20 is the opposite honesty case from Phase 19 — genuinely
  live-drilled, not just written to spec** — `pg_dump`/`pg_restore`/
  `psql` are real, available tools in this environment (unlike a Docker
  daemon), so the restore drill actually ran: real audit events generated
  through a real governance instance, a real `pg_dump`, a real
  `DROP DATABASE`/`CREATE DATABASE` destroying all of it, a real
  `pg_restore`, and a real `GET /audit/verify` afterward. The result —
  `{"valid":true,"events_checked":5}`, identical to the pre-destruction
  baseline — is the actual output of that one run, not a predicted one.
  Scoped deliberately to `governance`'s own database, the one service
  whose post-restore correctness has a cheap, structural check (the hash
  chain); the other ten logical databases are backed up by the same
  script but not independently drill-verified this phase, named as an
  explicit, un-covered gap rather than silently assumed fine. Full detail
  in `docs/phase-20-backup-disaster-recovery.md` and
  `services/governance/README.md`.
- **Phase 13's Health Monitor and Metrics Dashboard have no write path
  to anything** — every number is computed live from six small, real
  listing endpoints added to earlier services (none of which gained a
  new write surface). Confirmed live at every layer: a dead peer service
  never blinds the rest of an aggregate response, a stuck task is
  flagged only once it genuinely exceeds a real, configurable time
  threshold (never a stored "SLA flag" — Phase 2 never built one, so
  this is computed from real timestamps instead of assuming a field that
  doesn't exist), and every metrics category reflects genuine activity —
  a real completed task's real latency, a real approval's real
  time-to-decision, a real db query's real capability attribution. Two
  real bugs caught along the way: `clients.get_tasks()` had no
  Authorization header at all (Phase 2's Gateway requires one; the
  failure was silently swallowed by the same broad exception handling
  that keeps one dead dependency from blinding the rest of a response,
  so it looked like "no tasks exist" rather than "this call was
  rejected"), and a naive-vs-aware datetime comparison broke the first
  time a peer service happened to be running on SQLite rather than
  Postgres (SQLite drops timezone info on round-trip — the same class of
  gap Phase 1's own Postgres honesty notes already name). `POST
  /health/alert-config` persists an alerting *intent* only — no real
  notification channel exists anywhere in this codebase yet, and that's
  said plainly rather than implied to work. Full detail in
  `services/observability/README.md`.
- Every "what's a stub" note in each service's own README is there because
  it materially affects what you should and shouldn't trust yet — read
  those before deploying anything here for real.

## Contributing to this repo

Commit history mirrors the actual build order: each phase's design doc
landed first, then its implementation, with follow-up commits wherever a
later phase surfaced a real gap in an earlier one — Phase 2 needed new
policy rules in `governance`; Phase 3 needed `/security/classify` and
`GET /approval/{id}`; Phase 6 needed shell/git policy rules; Phase 7
needed `secrets.resolve` in `governance` (a genuine gap the doc names but
Phase 1 never built) plus a fix to Phase 5's own Reasoning Engine loop
(the schema-retry path was silently discarding tool-call context); Phase
8 needed a `GET /capabilities` introspection endpoint on `agents`, a
`planner` policy role in `governance`, a fix to a latent Pydantic v2 bug
in Phase 5's `ExecuteRequest` that no earlier caller happened to trigger,
and two structural routing overrides in Reasoning Engine once a live
model reasonably applied individual-agent instructions (`delegate_to`,
self-assessed `risk_classification`) to a routing-only capability they
were never meant for; Phase 9 extended Phase 7's `GET /db/schema/{target}`
to return foreign keys, not just column names, since ERP Knowledge
Engine's structured relationship graph needed real data Phase 7 never
had a reason to expose. Phase 10 needed a genuinely new governance
mechanism (`POST /security/verify_environment`, Testing Agent's
structural sandbox-vs-production gate) and one real policy-file bug fix
(`devops_agent` was missing `shell.execute: allow` even though `git.*`
was present, since Git Manager's own calls re-check `shell.execute` for
the same capability at the Shell Executor layer) — but otherwise reused
Phase 6's and Phase 7's execution bridges completely unchanged for all
four new agents' `propose_*` actions, the strongest evidence yet that
the shared-infrastructure bet made in Phases 4–8 was the right one.
Phase 11 needed one small, genuinely new endpoint in `assembly`
(`GET /context/model-ceiling`, exposing Context Builder's existing
model-isolation check over HTTP so `knowledge_pipelines` could reuse it
rather than duplicate it) plus new policy rules in `governance` for
`code_analysis.raw_source_request` and a `git_manager` system role — but
its own two-tier structural/raw-source split, the whole point of the
phase, needed no changes to any earlier phase at all, closing the loop
Phase 10 explicitly flagged (Django Agent's documentation-only
limitation) with new code contained entirely within
`knowledge_pipelines`. Phase 12 (a genuinely new service,
`services/extensibility/`) needed one small, real change outside itself
— `agents/reasoning_engine/capability_registry.py` gained a second,
configurable glob directory so an approved plugin's `capability.yaml`
is discoverable without touching how discovery itself works — otherwise
its entire lifecycle (register, approve, activate, invoke; install,
approve, activate, auto-disable) is self-contained. Phase 14 needed
zero new bridge code for two of its three agents (Inventory Agent and
Accounting Agent both reuse existing bridges completely unchanged) and
one small (~15-line) new bridge for the third (Costing Agent, wrapping
Phase 9's existing formula registration) — but surfaced two real,
independent permission-boundary gaps live testing alone could catch:
`secrets_registry.yaml`'s allow-list and Shell Executor's allowlist
files are both separate from governance's own `roles:` policy, and a
new agent needs updating in all of them, not just one. Phase 13
needed one small, real listing endpoint on each of six earlier services
(`governance`, `agents`, `knowledge`, `knowledge_pipelines`, `execution`,
`database`) — every one of them had a write path and a single-record
lookup already, but none had ever needed to *list* more than one record
at a time until an aggregator showed up wanting to. Two more real bugs
surfaced only by actually running the result against live services: a
missing bearer token on a call to Phase 2's Gateway, and a naive/aware
datetime comparison that only breaks against a SQLite-backed peer, not
a Postgres one — both fixed and locked in as regressions. Phase 15
needed one small, genuinely new endpoint on `platform-spine`
(`GET /api/v1/tasks/{task_id}/events`, exposing Task Manager's own
`task_events()` — real since Phase 2, never reachable over HTTP until
Project Management Agent's `task.read` tool call needed the real
transition history, not just the current-status snapshot) plus a real,
independent second dimension on `database`'s existing classification
scoping (PII, orthogonal to public/internal/confidential) — and its own
first live test caught a genuine design bug in that new mechanism
itself: the PII gate initially sat *on top of* the ceiling gate instead
of being truly independent, silently defeating the entire point for any
capability deliberately kept at a low ceiling. Phase 16 needed one
genuinely new mechanism in `governance` (a second agent's structured
review attaching to another agent's pending approval, append-only,
never touching the approval's own decision) plus two of its own new
tool calls in `agents` reusing entirely existing, already-built
endpoints on two OTHER services (`execution`'s read-only `/git/diff`,
`knowledge_pipelines`'s `/graph` and `/docs/ingest`) — zero code changes
needed in either of those two services, both endpoints had simply never
had a real caller before. Live testing caught two bugs in the new
caller code itself, not in what it called: `/graph` resolves caller ids
to real names while `/symbol/{ref}`'s own callers list doesn't, so the
first version picked the wrong one of two existing endpoints; and a
bare branch name diffs against the working tree, not `main`, unless the
caller builds that comparison explicitly. Phase 17 needed one genuinely
new artifact type in `execution` (real, reviewed, deterministic scripts
under `shell_executor/scripts/`, invoked through the exact same
sandboxed-command path every other allowlisted tool already uses — not
a new execution mechanism, just a new kind of thing that mechanism
runs) plus one small, real gap-fill in `knowledge_pipelines`
(`GET /erp-knowledge/formula/by-name/{name}` — the underlying store
function existed since Phase 14, reachable over HTTP for the first time
only once a model genuinely needed to resolve a formula by name rather
than by id). Live testing caught a bug neither in the new scripts nor
in what they called: a literal JSON example in a prompt template
collided with Prompt Builder's own `str.format()`-based rendering,
breaking every single render for that agent, not just the one
demonstrating a formula — invisible from reading the template file
alone, since nothing about a plain-language example looks like code.
Phase 18 needed one small, real gap-fill in `governance`
(`correlation_id` on `GET /audit/query` — the standard way this system
already threads a task's related events together, reachable as a filter
for the first time only once Security Agent's own real tool call needed
a complete trail for one specific task) plus one confirmation that an
earlier phase's own bridge (`reverse_eng_bridge.py`, Phase 16) was
built generically enough to reuse for a second, unrelated agent
(Documentation Agent) with zero code changes — the strongest evidence
yet that the reuse-first discipline this project has followed since
Phase 10 keeps paying off. That pattern —
build the phase that unblocks what already exists before adding more
surface area, and trust live testing over code review to find the gaps
between files that individually look correct, including gaps in a
mechanism you just wrote this same phase — is the intended way to
keep extending this. Phase 19 breaks that pattern in one honest way
worth naming: it touches no application code in any earlier service at
all, and there was nothing to live-test it against, since no Docker
daemon exists in this environment. What verification it does have is
real — every compose env var cross-checked line-by-line against what
each service's own README already documents needing — but it's
structural cross-referencing, not the "ran it and watched it work" bar
every phase before it cleared. Said plainly here rather than implied
away by reusing the same confident language the tested phases earned.
