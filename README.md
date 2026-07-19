# AI Operating System

A private, offline-first AI orchestration layer for a large engineering ERP
(Odoo 19 + Django), coordinating specialized agents instead of one giant
model. Governance-first: nothing executes without passing through Security
Layer, and every mutating action is logged and approval-gated before it
touches anything real.

Designed and built one subsystem at a time — see [`docs/`](docs/) for the
full phase-by-phase architecture (why each decision was made, alternatives
considered, trade-offs, security implications) before diving into code.

## Status

| Phase | Subsystem | Design doc | Code |
|---|---|---|---|
| 1 | Security Layer, Audit Logger, Human Approval Layer | [`docs/phase-1-governance-layer.md`](docs/phase-1-governance-layer.md) | [`services/governance/`](services/governance/) — 17 tests |
| 2 | Configuration Manager, Gateway, Task Manager | [`docs/phase-2-gateway-task-manager-config.md`](docs/phase-2-gateway-task-manager-config.md) | [`services/platform-spine/`](services/platform-spine/) — 21 tests |
| 3 | Memory Manager, Vector Search | [`docs/phase-3-memory-vector-search.md`](docs/phase-3-memory-vector-search.md) | [`services/knowledge/`](services/knowledge/) — 22 tests |
| 4 | Context Builder, Prompt Builder | [`docs/phase-4-context-prompt-builder.md`](docs/phase-4-context-prompt-builder.md) | [`services/assembly/`](services/assembly/) — 26 tests |
| 5 | Reasoning Engine, Odoo Agent | [`docs/phase-5-odoo-agent-reasoning-engine.md`](docs/phase-5-odoo-agent-reasoning-engine.md) | [`services/agents/`](services/agents/) — 27 tests |
| 6 | Shell Executor, Git Manager | [`docs/phase-6-shell-git-manager.md`](docs/phase-6-shell-git-manager.md) | [`services/execution/`](services/execution/) — 45 tests |
| 7 | Database Connector, Database Agent | [`docs/phase-7-database-connector-agent.md`](docs/phase-7-database-connector-agent.md) | [`services/database/`](services/database/) — 39 tests (Database Agent itself lives in `services/agents/agents/database_agent/`) |
| 8 | Planner, Capability Registry | [`docs/phase-8-planner-capability-registry.md`](docs/phase-8-planner-capability-registry.md) | [`services/planning/`](services/planning/) — 27 tests (Planner itself lives in `services/agents/agents/planner/`) |
| 9 | Documentation Engine, ERP Knowledge Engine | [`docs/phase-9-documentation-erp-knowledge-engine.md`](docs/phase-9-documentation-erp-knowledge-engine.md) | not yet built |
| 10 | Django, DevOps, Docker, Testing Agents | [`docs/phase-10-django-devops-docker-testing-agents.md`](docs/phase-10-django-devops-docker-testing-agents.md) | not yet built |
| 11 | Code Analysis Engine | [`docs/phase-11-code-analysis-engine.md`](docs/phase-11-code-analysis-engine.md) | not yet built |
| 12–21 | Extensibility, observability, remaining agents, deployment, backup/DR, consolidated reference | [`docs/phases-12-21-remaining-subsystems.md`](docs/phases-12-21-remaining-subsystems.md) | not yet built |

Eight services are real, tested code today; everything past Phase 8 is
fully designed but not yet implemented.

## Running what exists

Each service is independently runnable and has its own README with real
run/test instructions. Dependency order: `governance` has none;
`platform-spine` and `knowledge` both call `governance`; `assembly` calls
all three of the others; `execution` and `database` each call only
`governance` directly; `planning` calls `governance`, `agents` (to sync
its capability roster and run Planner), and `platform-spine` (to create
real subtasks); `agents` calls all of the above plus a local Ollama
instance, and calls back into `execution` (an approved code change),
`database` (an approved data write or migration), and `planning` (to
fetch the live capability roster Planner reasons over) — closing all
three loops end to end.

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

# terminal 5
cd services/execution && pip install -r requirements.txt
SECURITY_LAYER_URL=http://localhost:8000 SANDBOX_ROOT=/tmp/ai_os_sandbox \
uvicorn main:app --port 8006

# terminal 6 — governance's secrets_registry.yaml maps target_db "demo_erp"
# to this env var (set it wherever governance itself runs, not here)
cd services/database && pip install -r requirements.txt
SECURITY_LAYER_URL=http://localhost:8000 \
uvicorn main:app --port 8007

# terminal 7 — needs Ollama running locally with a model pulled
cd services/agents && pip install -r requirements.txt
SECURITY_LAYER_URL=http://localhost:8000 PLATFORM_URL=http://localhost:8002 \
KNOWLEDGE_URL=http://localhost:8003 ASSEMBLY_URL=http://localhost:8004 \
EXECUTION_URL=http://localhost:8006 PROPOSAL_REPO_PATH=/tmp/ai_os_sandbox/your-real-repo-clone \
DATABASE_CONNECTOR_URL=http://localhost:8007 CAPABILITY_REGISTRY_URL=http://localhost:8008 \
uvicorn main:app --port 8005

# terminal 8
cd services/planning && pip install -r requirements.txt
SECURITY_LAYER_URL=http://localhost:8000 AGENTS_URL=http://localhost:8005 PLATFORM_URL=http://localhost:8002 \
uvicorn main:app --port 8008
# once agents is up: curl -X POST localhost:8008/capabilities/sync
```

All default to SQLite with zero setup. Point `DATABASE_URL` at Postgres
for the real deployment target — each service's README has the exact
connection string format and what's been verified against it (including
`knowledge`'s use of real pgvector, not a stand-in).

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
were never meant for. That pattern — build the phase that unblocks what
already exists before adding more surface area — is the intended way to
keep extending this.
