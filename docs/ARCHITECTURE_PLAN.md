# AIOS Orchestration & Memory — Real State, Not a Restructure Proposal

## Why this file was rewritten

A previous, uncommitted draft of this file (never merged, found untracked
in the primary worktree) analyzed `services/` and concluded the project
was "60% implemented" and lacked a unified "Orchestration Core," then
proposed building a new `services/orchestrator/` with `core.py` (task
routing), `agents_manager.py`, and `approval_engine.py`.

That premise is factually wrong, checked against the actual code, not
against a file listing. This project has 31 fully built, real,
live-tested phases (see `docs/aios-architecture-and-phases.md` — the
primary reference, `docs/README.md` for the reading order). The
orchestration core, the multi-agent delegation logic, and the
human-in-the-loop approval engine the old draft proposed all already
exist:

| What the old draft proposed | What already exists, real and tested |
|---|---|
| `orchestrator/core.py` — task routing (simple query → RAG; complex → multi-agent) | `services/agents/agents/reasoning_engine/` (Phase 5) — the real shared execution core every one of 25+ agents runs through, plus `services/agents/agents/reasoning_engine/model_router.py` (Phase 23) for model-tier routing |
| `orchestrator/agents_manager.py` — role-based delegation | `services/planning/` (Phase 8) — Planner + Capability Registry, real dynamic task decomposition and routing over a live agent roster; `delegate_to` in the shared 6-field output schema (Phase 4/5) for single-capability handoff |
| `orchestrator/approval_engine.py` — human-in-the-loop gates | `services/governance/` (Phase 1) — Security Layer, Audit Logger, Human Approval Layer; every mutating action in this system already routes through `authorize() → audit_log() → (approval if required)`, since before any agent existed |
| Saved, re-triggerable multi-agent flows | `services/planning/planning/workflows/` (Phase 30) — declarative workflow YAML, real dispatch/advance, reusing Phase 8's own task-graph schema |

Building a new `services/orchestrator/` as the old draft describes would
not add a missing capability — it would duplicate `services/planning/`
and `services/agents/agents/reasoning_engine/` with a second, competing
implementation of the same routing/delegation/approval logic, violating
this project's own `add-new-service` skill (design doc first, justify
why an existing service can't be extended) and the concentric-rings
architecture already documented in `docs/architecture-vision.md` §1
(governance + kernel, permanent; agents, configuration; adapters,
replaceable). **This is not being built.**

## What was actually investigated: the old draft's real "Phase 2" ideas

The old draft's "Phase 2: Advanced Integration & Self-Improvement" named
two ideas independent of the orchestrator proposal. Both were checked
against the real code before deciding what, if anything, to build.

### Cross-Agent Memory Sharing — substantially already built, not a gap

The old draft framed this as missing: "allow agents from different
projects to share a global Project Knowledge Graph while maintaining
privacy boundaries via vector DB isolation." Checked against
`services/knowledge/knowledge/vector_search/`:

- `Document.project_id` is a real, indexed, non-nullable column —
  ingestion always requires it, and `query()` filters on it server-side
  when a `namespace` is supplied (`index.py`: "Classification and
  project filtering happen here, server-side... not a post-filter the
  caller could bypass").
- `services/assembly/assembly/context_builder/`'s `gather_candidates()`
  always threads a required `namespace` through to both memory and
  vector queries — every agent going through Context Builder (i.e.,
  every agent) already gets project-scoped retrieval, not a single
  unscoped global index.
- ERP schema knowledge (Phase 9) is already namespaced by
  `project_id=target_db` per target database.

The one real, honest gap: `namespace`/`project_id` is a caller-supplied
convention, not an auth-enforced hard boundary — nothing currently stops
a caller from passing the wrong namespace or none at all. That is a
real, narrow finding, not the "genuinely missing layer" the old draft
described. Not scheduled as its own phase; worth a small, targeted note
in `services/knowledge/README.md` if it becomes a live problem.

### Schema Drift Detector — a genuine gap, closed as Phase 32

The old draft's other idea: auto-detect changes in Odoo/Django schemas
and trigger re-indexing without manual intervention. Checked against
`services/knowledge_pipelines/knowledge_pipelines/erp_knowledge_engine/`:
`odoo_sync.py`'s `sync()` has always been purely manually-triggered
(`POST /erp-knowledge/sync`) — nothing compared a freshly-fetched live
schema against the previously stored snapshot to decide whether
anything had actually changed before unconditionally re-ingesting every
table.

This was real and worth building. See
`docs/aios-architecture-and-phases.md#phase-32-schema-drift-detection`
for what shipped: `drift.py`'s real structured table/column diff against
`ErpSchemaSnapshot.tables`, and `GET /erp-knowledge/{target_db}/drift`
(read-only check) + `POST /erp-knowledge/{target_db}/check-and-sync`
(only re-syncs when genuine drift is found). Explicit, on-demand
functions — not a background daemon. This project has never had one
anywhere (confirmed exhaustively during Phase 30's own dispatcher
design: Task Manager's `dequeue()` has zero callers, and nothing
schedules itself); a human, cron job, or external scheduler decides
when to call `check-and-sync`, matching the same "poll-triggered, not
continuously-running" posture `knowledge_pipelines/README.md` already
established for document-source watching.
