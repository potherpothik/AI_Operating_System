# Phase 21 — Consolidated Reference

---

## Prerequisites (read before implementation)

| Doc | Why |
|---|---|
| [`docs/README.md`](README.md) | Doc index and before-you-code checklist |
| [`phases-12-21-remaining-subsystems.md`](phases-12-21-remaining-subsystems.md) Part D | The original, speculative version of this same reference — written before Phases 1–20 existed as real code |
| [`architecture-vision.md`](architecture-vision.md) | Kernel map and brain grouping this doc's component diagram restates in as-built form |

---

## 0. Priority Decision: Why This Phase Now, and What It Actually Is

**Why it exists here:** Part D of `phases-12-21-remaining-subsystems.md` (component diagram, API surface index, DB schema index, folder structure, canonical message format) was written speculatively, before any of Phases 1–20 existed as real code. Every prior phase's own README already carries an honest per-service account of what's real; this phase's only job is to replace that one speculative, all-in-one reference with the equivalent view **regenerated from the real, running source** — not to design anything new.

**Method, not guesswork:** every table below was produced by grepping the actual source, not recalled from the original design doc or from memory of writing it:
- API surface index — `grep -rn "APIRouter(prefix=" services/*/*/*/api.py` for base paths, then `grep -n "@router\.\(get\|post\|put\|delete\|patch\)"` per file for every real route.
- DB schema index — `grep -n "__tablename__"` across every `models.py` in the repo.
- Component/dependency diagram — the real `depends_on` graph in `docker-compose.yml` (Phase 19), not a hand-drawn approximation.
- Agent capability count — `find services/agents/agents -maxdepth 2 -iname capability.yaml | wc -l`.
- Canonical message format — the literal string in `services/assembly/assembly/prompt_builder/shared_fragments.py`'s `REFUSE_DELEGATE_APPROVAL_FRAGMENT`, the fragment every agent template actually renders with.

**Alternatives considered**
- *Editing Part D of the original consolidated doc in place* — rejected, matching the pattern already established for Phases 15–20: each gets its own dedicated doc once it's real, and the original doc is left as the historical speculative record rather than silently rewritten.
- *Treating this as a new design phase with alternatives/trade-offs to weigh* — rejected. There is no new mechanism to design here; the entire deliverable is an accurate snapshot of Phases 1–20's real, already-built interfaces. Sections below skip the "alternatives considered" framing where there genuinely were none.

**What this phase found:** the real system matches the original speculative design far more closely than most prior phases' own "what changed" sections would suggest — every one of the 21 real API prefixes matches Part D's table exactly. The genuine divergences (Section 4) are narrow and specific, not systemic.

**Estimated complexity:** Low — this is regeneration and cross-checking, not new code.

---

## 1. Component Diagram (real, from `docker-compose.yml`'s own `depends_on` graph)

```
                                   ┌─────────────┐
                                   │  postgres    │  ← one instance, 11 logical DBs
                                   └──────┬───────┘         (Phase 19)
                                          │
                    ┌─────────────────────┼───────────────────────────┐
                    ▼                                                  │
            ┌───────────────┐                                         │
            │  governance    │  Security / Audit / Approval (Phase 1)  │
            │  (no deps)     │◄────────────────────────────────────────┤ authorizes
            └───────┬────────┘                                        │ everything
                     │ depended on by every other service               │ below
     ┌───────────────┼────────────────────┬─────────────┬──────────────┼───────────────┐
     ▼               ▼                    ▼             ▼              ▼               ▼
┌──────────┐  ┌───────────┐        ┌───────────┐  ┌───────────┐ ┌──────────┐   ┌──────────────┐
│ platform-│  │ knowledge  │        │ database   │  │extensibil-│ │execution │   │knowledge_    │
│ spine     │  │ (memory,   │       │ (Phase 7)  │  │ity (mcp,  │ │(shell,   │   │pipelines     │
│ (Phase 2) │  │ vector)    │       │            │  │plugins;   │ │git;      │   │(docs, erp-   │
│           │  │ (Phase 3)  │       │            │  │Phase 12)  │ │Phase 6)  │   │knowledge,    │
└─────┬─────┘  └─────┬─────┘        └───────────┘  └─────┬─────┘ └────┬─────┘   │code-analysis;│
      │               │                                   │ needs      │ needs   │Phase 9/11)   │
      │               │                                   │ assembly   │ needs   └──────┬───────┘
      ▼               │                                   │ + agents   │ know-          │
┌───────────┐         │                                   │            │ ledge_          │
│ assembly   │◄────────┘ needs governance+platform-spine+  │            │ pipelines        │
│ (context,  │           knowledge                         │            │ (dxf/cutlist       │
│  prompt;   │                                              │            │  scripts)            │
│  Phase 4)  │                                              │            └──────────────────────┘
└─────┬──────┘                                                            ▲
      │ needed by agents, extensibility                                   │
      ▼                                                                   │
┌────────────────────────────────────────────────────────────┐            │
│  agents  (Reasoning Engine + 23 agent capabilities;          │           │
│  Phases 5, 10, 14–18) — depends on governance, platform-     │           │
│  spine, knowledge, assembly, execution, database,             │──────────┘
│  knowledge_pipelines, ollama, postgres                          │
└──────────────────────────┬────────────────────────────────────┘
                            │ needed by planning, extensibility, observability
                            ▼
                     ┌─────────────┐        ┌──────────────┐
                     │  planning    │        │   ollama      │  local model runtime
                     │  (Phase 8)   │        │  (no deps)    │  (Phase 5+)
                     └─────────────┘        └──────────────┘

observability (Phase 13) depends on ALL ten other application services + postgres —
it's the one service that reads across the whole system (health/metrics aggregation),
never the other way around.
```

Real service list (11 FastAPI services, `services/*/`): `governance`, `platform-spine`,
`knowledge`, `assembly`, `agents`, `execution`, `database`, `planning`,
`knowledge_pipelines`, `extensibility`, `observability` — plus `ollama` and `postgres`
as non-application containers (Phase 19). This differs from Part D's illustrative
diagram in module count and shape (Part D sketched three separate governance-ish
boxes and a generic "22 Agents" box); the real system is 11 services and 23 agent
capabilities, named in full below.

---

## 2. Real Folder Structure

```
AI_Operating_System/
├── services/
│   ├── governance/            # Phase 1  — security/, audit/, approval/
│   ├── platform-spine/        # Phase 2  — config_manager/, gateway/, task models
│   ├── knowledge/             # Phase 3  — memory_manager/, vector_search/
│   ├── assembly/               # Phase 4  — context_builder/, prompt_builder/
│   ├── agents/                   # Phase 5, 10, 14–18 — reasoning_engine/ + 23 agents/<name>/
│   ├── execution/                  # Phase 6  — shell_executor/, git_manager/
│   ├── database/                     # Phase 7  — database_connector/
│   ├── planning/                       # Phase 8  — planner/, capability_registry/
│   ├── knowledge_pipelines/              # Phase 9, 11 — documentation_engine/, erp_knowledge_engine/, code_analysis_engine/
│   ├── extensibility/                      # Phase 12 — mcp_client/, plugin_system/
│   └── observability/                        # Phase 13 — health_monitor/, metrics_dashboard/
├── deploy/                                     # Phase 19/20 — docker-compose.yml, Dockerfiles, postgres-init/, backup.sh, restore.sh
└── docs/                                         # this entire phase-by-phase design record
```

Real divergences from Part D's illustrative tree: no top-level `data/` (Phase 7 is
`services/database/`, following this repo's own `services/<name>/` convention
established from Phase 1 on); no top-level `config/`/`secrets/` directories —
non-secret policy lives per-service (`governance/security/policies/*.yaml`,
`database/database_connector/classification/pii_registry.yaml`), and secrets are
never committed at all, indirected through `secrets_registry.yaml`/
`environment_registry.yaml` (Phase 7/10) rather than a repo-root `secrets/` folder.

---

## 3. API Surface Index (real, every prefix and route grepped from source)

| Module | Base path | Real routes | Phase |
|---|---|---|---|
| Security Layer | `/security` | `POST /authorize`, `POST /classify`, `POST /secrets/resolve`, `POST /verify_environment`, `GET /policy/{role}`, `POST /reload` | 1 |
| Audit Logger | `/audit` | `POST /log`, `GET /query` (+ `correlation_id` filter, Phase 18), `GET /verify` | 1 |
| Human Approval Layer | `/approval` | `POST /request`, `GET /pending`, `GET` (bare, Phase 13), `GET /{id}`, `POST /{id}/attach_review` (Phase 16), `POST /{id}/decide` | 1 |
| Configuration Manager | `/config` | `GET /{service}`, `POST /reload`, `POST /override`, `GET /schema/{service}` | 2 |
| Gateway | `/api/v1` | `POST /tasks`, `GET /tasks/{id}`, `GET /tasks`, `POST /tasks/{id}/status`, `GET /tasks/{id}/events`, `GET /tasks/{id}/stream` | 2 |
| Memory Manager | `/memory` | `POST /{type}/write`, `GET /{type}/read`, `POST /{type}/query`, `DELETE /{type}/{id}`, `GET /{type}/retention-policy`, `GET /types`, `POST /{type}/reconcile-approvals` | 3 |
| Vector Search | `/vector` | `POST /ingest`, `POST /query`, `DELETE /{document_id}`, `POST /reindex/{document_id}`, `GET /stats` | 3 |
| Context Builder | `/context` | `POST /build`, `GET /model-ceiling`, `GET /{context_id}`, `POST /pin` | 4 |
| Prompt Builder | `/prompt` | `POST /templates`, `GET /templates`, `POST /templates/reconcile-approvals`, `POST /render`, `POST /validate-response` | 4 |
| Reasoning Engine | `/reasoning` | `POST /execute`, `GET /executions`, `GET /{execution_id}/trace`, `POST /{execution_id}/resume` | 5 |
| Shell Executor | `/shell` | `POST /execute`, `GET /executions`, `GET /{sandbox_id}/status`, `POST /{sandbox_id}/kill` | 6 |
| Git Manager | `/git` | `POST /branch`, `POST /commit`, `POST /diff`, `POST /push`, `POST /open_mr` | 6 |
| Database Connector | `/db` | `POST /query`, `POST /dry_run`, `POST /write`, `POST /migrate`, `GET /query-log`, `GET /schema/{target}` | 7 |
| Capability Registry | `/capabilities` | `GET` (bare), `GET /{id}`, `POST /register`, `POST /{id}/deprecate`, `POST /{id}/deprecate/confirm`, `POST /sync`, `POST /reconcile-approvals` | 8 |
| Planner | `/planner` | `POST /plan`, `POST /replan`, `GET /capabilities`, `GET /{task_graph_id}` | 8 |
| Documentation Engine | `/docs` | `POST /ingest`, `POST /watch`, `GET /sources`, `POST /sources/{id}/check`, `POST /classify-override`, `POST /classify-override/{approval_id}/confirm` | 9 |
| ERP Knowledge Engine | `/erp-knowledge` | `POST /sync`, `POST /annotate`, `GET /snapshots`, `GET /graph`, `POST /formula/register`, `GET /formula/by-name/{name}` (Phase 17, registered before the next route), `GET /formula/{formula_id}` | 9, 17 |
| Code Analysis Engine | `/code-analysis` | `POST /scan`, `GET /symbol/{ref}`, `GET /graph`, `POST /raw-source-request`, `POST /raw-source-request/{id}/fetch` | 11 |
| MCP Client | `/mcp` | `POST /register`, `POST /servers/{id}/activate`, `GET /servers`, `POST /invoke` | 12 |
| Plugin System | `/plugins` | `POST /install`, `POST /{id}/activate`, `POST /{id}/disable`, `POST /{id}/report-error`, `GET` (bare) | 12 |
| Health Monitor | `/health` | `GET /system`, `GET /{module}`, `POST /alert-config` | 13 |
| Metrics Dashboard | `/metrics` | `GET /overview`, `GET /export`, `GET /{category}` | 13 |

All 21 base paths match Part D's original speculative table exactly — the routes
underneath them are the real detail Part D never had, since it predates the code
that defines them. Phases 14–20 added no new API modules of their own (they extend
existing modules' policy/data, or in Phase 19/20's case are deployment artifacts,
not FastAPI routes) — see Section 4 for exactly which endpoints those phases added
to already-listed modules.

---

## 4. Database Schema Index (real, every `__tablename__` grepped from source)

| Tables | Owning module | Phase |
|---|---|---|
| `audit_event`, `approval_request`, `approval_review` (Phase 16), `test_execution_target` (Phase 10) | Security / Audit / Approval | 1, 10, 16 |
| `task`, `task_event`, `config_override` | Task Manager / Config | 2 |
| `memory_record`, `decision_record` | Memory Manager | 3 |
| `document`, `chunk` | Vector Search | 3 |
| `context_package`, `context_item`, `pinned_fact` | Context Builder | 4 |
| `prompt_template`, `prompt_render_log` | Prompt Builder | 4 |
| `reasoning_execution`, `reasoning_step`, `agent_capability_def` | Reasoning Engine | 5 |
| `sandbox_execution` | Shell Executor | 6 |
| `git_action` | Git Manager | 6 |
| `db_query_log`, `db_dry_run`, `db_write`, `db_migration_request` | Database Connector | 7 |
| `task_graph`, `subtask` | Planner | 8 |
| `capability_registry_entry` | Capability Registry | 8 |
| `doc_source`, `doc_ingestion_log` | Documentation Engine | 9 |
| `erp_schema_snapshot`, `erp_field_annotation`, `erp_formula` | ERP Knowledge Engine | 9, 17 |
| `code_symbol`, `call_edge`, `raw_source_request`, `analysis_run` | Code Analysis Engine | 11 |
| `mcp_server`, `mcp_invocation` | MCP Client | 12 |
| `plugin` | Plugin System | 12 |
| `alert_config`, `health_poll_log` | Health Monitor | 13 |

**Real, named divergence from Part D:** Part D's table listed `role`,
`role_permission` under Security/Audit/Approval. Those tables were never built —
`services/governance/README.md` has said so plainly since Phase 1: policy is a
single YAML file (`governance/security/policies/default.yaml`), reloaded via
`POST /security/reload`, not database-backed RBAC. This isn't a regression from
the design; it was a deliberate simplification made and documented back in
Phase 1, and Part D's table was simply never updated to reflect it. Similarly,
PII scoping (Phase 15) and secrets/environment indirection (Phases 7, 10) are
real mechanisms but live in YAML registries
(`database_connector/classification/pii_registry.yaml`,
`governance/security/secrets_registry.yaml`, `.../environment_registry.yaml`),
not database tables — none of Part D's schema table ever claimed otherwise, so
there's nothing to correct there, only to note as a real design choice worth
naming explicitly in one place.

Metrics Dashboard (Phase 13) has no tables of its own, by design — every number
is computed live from other services' existing listing endpoints (documented in
its own README); a schema row for it would misrepresent that.

---

## 5. Real Agent Capability List (23, `services/agents/agents/<name>/capability.yaml`)

| Brain | Agents | Phase |
|---|---|---|
| Coding | `django_agent`, `devops_agent`, `docker_agent`, `testing_agent` | 10 |
| Coding | `code_review_agent`, `reverse_engineering_agent`, `architecture_agent` | 16 |
| Coding | `python_agent`, `documentation_agent`, `security_agent`, `research_agent` | 18 |
| ERP | `odoo_agent`, `database_agent` | 5, 7 |
| ERP | `costing_agent`, `accounting_agent`, `inventory_agent` | 14 |
| ERP | `manufacturing_agent`, `sales_agent`, `project_management_agent` | 15 |
| ERP | `calculation_agent`, `cutlist_optimization_agent`, `autocad_agent` | 17 |
| Shared | `planner` | 8 |

(`reasoning_engine/` itself is not an agent — it's the shared dispatch loop every
agent above runs through; it has no `capability.yaml`.)

---

## 6. Agent Communication Protocol (real)

Confirmed unchanged from the original design: agents never call each other
directly. `reasoning_engine/loop.py` reads a `delegate_to` field from the model's
own structured output (`parsed.get("delegate_to")`); when present and the
current capability isn't `planner` itself, the loop returns a `"delegate"`
routing decision rather than treating the response as final — Planner (Phase 8)
is the only thing that turns a delegation signal into a new routed subtask.
This is the same indirection Part D described: no agent's code has to know
another agent exists, only Capability Registry and Planner's routing logic do.

**Real, additional mechanism Part D didn't anticipate** (Phases 5–18): a second,
narrower kind of "handoff" exists alongside delegation — the **tool-call bridge**
pattern. When a model's structured output names a real, executable action
(`db.propose_write`, `git.propose_change`, `security.audit_query`, a formula
lookup, a cutlist optimization, etc.) and includes the fresh input that action
needs, `loop.py` dispatches to the matching bridge module (`execution_bridge`,
`database_bridge`, `review_bridge`, `security_bridge`, `calc_bridge`,
`cutlist_bridge`, `autocad_bridge`, `erp_bridge`, and others under
`reasoning_engine/`), which calls the real downstream service over HTTP and
feeds the real result back into the SAME agent's next turn — never treated as
that turn's final answer, never routed through Planner. This is a within-agent
tool call, not an inter-agent delegation; Part D's `delegate_to` mechanism and
Canonical Message Format (Section 7 below) both predate this pattern entirely,
since it only became necessary once agents needed to actually call real
services (Phase 6 onward) rather than just producing advisory text.

---

## 7. Canonical Message Format (real, from `prompt_builder/shared_fragments.py`)

Every agent template renders this exact fragment
(`REFUSE_DELEGATE_APPROVAL_FRAGMENT`) verbatim — not reconstructed from memory,
the literal source:

```json
{
  "reasoning": "your reasoning, in your own words",
  "answer_or_proposal": "your actual answer or proposed action",
  "confidence": <float 0.0-1.0>,
  "provenance": [<ids of context items you actually used>],
  "risk_classification": "informational" | "low" | "medium" | "high",
  "delegate_to": <capability name, or null>
}
```

This matches Part D's illustrative format exactly, field for field. Each agent's
own `template.md` adds exactly one more required field on top — `"action"`,
naming which of that agent's declared, policy-checked actions the response
corresponds to (e.g. Odoo Agent's `"odoo.read_orm" | "odoo.explain_rule" |
"odoo.propose_change"`) — checked against the capability's permitted action list
before `loop.py` does anything with the response. Tool-call actions (Section 6)
add further action-specific fields on top of that (`sql_template`,
`shell_command`, `formula_name`, `dxf_path`, and so on) — real, but specific to
each bridge, not part of the shared base format above.

---

## 8. What Phases 14–20 Actually Added to Already-Listed Modules

Not new API modules — real additions layered onto the 21 modules already in
Section 3:

- **Phase 14** — `costing_agent`/`accounting_agent`/`inventory_agent` (Section 5); no new endpoints, new governance roles and `secrets_registry.yaml` entries only.
- **Phase 15** — `db.read_pii` policy action (governance) and `pii_registry.yaml` (Database Connector); task-events endpoint (`GET /tasks/{id}/events`, listed in Section 3 under Gateway).
- **Phase 16** — `POST /approval/{id}/attach_review` and `reviews: []` on `GET /approval/{id}` (both listed in Section 3).
- **Phase 17** — `GET /erp-knowledge/formula/by-name/{name}` (listed in Section 3, registered before the path-parameter route it could otherwise be swallowed by); real deterministic scripts under `services/execution/execution/shell_executor/scripts/` (`eval_formula.py`, `cutlist_solver.py`, `dxf_parse.py`) — not API routes, invoked through Shell Executor's existing `POST /shell/execute`.
- **Phase 18** — `correlation_id` filter on `GET /audit/query` (listed in Section 3).
- **Phase 19** — no API routes at all; `deploy/`-adjacent artifacts (`Dockerfile`s, `docker-compose.yml`) sitting outside every service's own code.
- **Phase 20** — no API routes at all; `deploy/backup.sh`, `deploy/restore.sh` — real, live-drilled shell scripts (`docs/phase-20-backup-disaster-recovery.md`).

---

## Next

Phase 22 — Coding Agent Gateway (OpenCode, Claude Code), already designed in
[`phase-22-external-coding-agents.md`](phase-22-external-coding-agents.md); the
next phase to actually build, following this same discipline (design doc first,
real implementation, real tests, honest README).
