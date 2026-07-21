# Architecture Vision — AI Operating System

### Engineering ERP Intelligence System · Two Brains on One Kernel

This document is the long-term picture. Phase-by-phase design docs in
[`docs/`](.) remain the source of truth for *how* each subsystem is built;
this file answers *what the whole thing is for* and where each piece fits.

---

## 0. What this system is

A private, offline-first **AI Operating System** for a large engineering ERP
(Odoo 19 + Django). It coordinates specialized agents instead of one giant
model. Governance-first: nothing executes without Security Layer, and every
mutating action is logged and approval-gated before it touches anything real.

The AI must eventually understand:

| Domain | Brain | Status |
|---|---|---|
| Odoo | ERP | Built (Phase 5) |
| Accounting / costing / inventory | ERP | Built (Phase 14) |
| Manufacturing / sales / project management | ERP | Built (Phase 15) |
| Operator control plane (chat, approvals, ops UI) | Shared | Built (Phase 24) — capability views and settings still designed only |
| Engineering calculations | ERP | Designed (Phase 17 `calculation_agent`) |
| Glass / fabrication / cutlist optimization | ERP | Designed (Phase 17 `cutlist_optimization_agent`) |
| Business workflows | ERP | Partial (ERP Knowledge Engine, Phase 9) |
| Databases | Shared | Built (Phase 7) |
| Django / Python | Coding | Built (Phase 10) |
| Docker / DevOps / Testing | Coding | Built (Phase 10) |
| Git repositories | Coding | Built (Phase 6 Git Manager) |
| React / frontend code quality | Coding | Designed (Phases 16–18) |
| External coding agents (OpenCode, Claude Code) | Coding | Built (Phase 22) — real safety gate, no live agentic session run in this environment |

---

## 1. Two brains, one kernel

```
AI Operating System
        │
 ┌──────┴────────┐
 │               │
ERP Brain     Coding Brain
 │               │
Odoo          Python / Django
Accounting    React
Inventory     Docker
Manufacturing Git
Projects      OpenCode / Claude Code (Phase 22)
Calculations
Cutlist / glass
```

Both brains run on the **same kernel services**. They are not separate
codebases. Grouping is declared on each agent via an optional field in
`capability.yaml`:

```yaml
capability: manufacturing_agent
brain: erp          # erp | coding
allowed_actions: [...]
```

Agent directories stay flat under `services/agents/agents/<name>/`. The
`brain` field is for Planner routing, Capability Registry filtering, and
human-readable docs — not a physical folder split.

---

## 2. Kernel component map

Vision names → what actually exists (or is still a gap):

| Vision component | Status | Where |
|---|---|---|
| Security Layer | Built | Phase 1 → `services/governance/` |
| Human Approval | Built | Phase 1 → `services/governance/` |
| Planner | Built | Phase 8 → `services/planning/` + `agents/planner/` |
| Context Builder | Built | Phase 4 → `services/assembly/` |
| Memory | Built | Phase 3 → `services/knowledge/` |
| ERP Knowledge | Built | Phase 9 → `services/knowledge_pipelines/` |
| Git Manager | Built | Phase 6 → `services/execution/` |
| MCP Manager | Built (as MCP Client / Plugin System) | Phase 12 → `services/extensibility/` |
| Metrics / Health (JSON APIs) | Built | Phase 13 → `services/observability/` |
| Control UI (Web Shell) | Built | Phase 24 → `services/control-ui/` + `web/` |
| Tool Router | Partial | Reasoning Engine routes `tool_call_request` (Phase 5); not a standalone module |
| Model Router | Built | Phase 23 → `services/agents/agents/reasoning_engine/model_router.py` — real typed registry + Ollama fallback; cloud providers real interface, honestly not_configured |

```
AI Kernel (existing services)
│
├── Planner              (planning + agents/planner)
├── Context Builder      (assembly)
├── Memory               (knowledge)
├── Tool Router          (reasoning engine routing — partial)
├── MCP Manager          (extensibility)
├── Git Manager          (execution)
├── ERP Knowledge        (knowledge_pipelines)
├── Security Layer       (governance)
├── Human Approval       (governance)
└── Model Router         (reasoning_engine/model_router.py — Phase 23)
```

---

## 3. Model strategy

Ollama-first, local models only by default:

```
Ollama
    │
    ├── Qwen
    ├── DeepSeek
    ├── Llama
    └── Future models
```

Today: `model_router.py` (Phase 23) resolves `default_local_model` /
`fallback_local_model` (or an explicit per-call `target_model` override)
against what's genuinely pulled in Ollama, via a typed `ModelType` registry
(`TEXT_LARGE`, `CODE`, `TEXT_EMBEDDING`, matching
[`elizaos-borrowed-ideas.md`](elizaos-borrowed-ideas.md) §5's own
`useModel(ModelType, …)` vocabulary) with priority-ordered fallback —
real, live-verified, not a design sketch. `TEXT_EMBEDDING` is named but not
rewired into `services/knowledge/`'s own embedding-model swap mechanism
(Phase 3) this phase.

External / cloud models have a real provider interface
(`OpenAIProvider`/`AnthropicProvider`/`GeminiProvider`) but are
deliberately never configured in this build — no real API key this
offline-first system sets, no real external call added. When a real
cloud provider is genuinely wired in, it remains approval-gated by
Security Layer classification rules (never send source code externally
without explicit approval) exactly as `assembly/context_builder/classification.py`
already enforces.

---

## 4. Domain roadmap

**Built today:** every phase in the original mandate, 1–24 (governance,
platform spine, memory,
assembly, agents + Reasoning Engine, execution, database, planning,
knowledge pipelines, extensibility/MCP, observability metrics/health,
costing/accounting/inventory agents, manufacturing/sales/PM agents,
code-review/reverse-engineering/architecture agents, calculation/cutlist-
optimization/AutoCAD agents, python/documentation/security/research agents,
Coding Agent Gateway, Model Router, Control UI), plus
real Phase 19 deployment artifacts (`Dockerfile`s, `docker-compose.yml`) —
written to the real interface but genuinely unbuilt/unverified against a
live Docker daemon, which doesn't exist in this environment; a different
honesty tier than the tested phases, named as such. Phase 20's backup/
restore scripts (`deploy/backup.sh`, `deploy/restore.sh`) are a third
honesty tier of their own: real, live-drilled against this environment's
own Postgres instance (`pg_dump`/`pg_restore` ARE available here, unlike
a Docker daemon) — see [`aios-architecture-and-phases.md#phase-20-backup-strategy-disaster-recovery`](aios-architecture-and-phases.md#phase-20-backup-strategy-disaster-recovery)
Section 3 for the real drill result. Phase 21 regenerates the original
speculative component diagram, API surface index, and DB schema index
from the real, grepped source — see
[`aios-architecture-and-phases.md#phase-21-consolidated-reference`](aios-architecture-and-phases.md#phase-21-consolidated-reference).
Phase 22 (Coding Agent Gateway) is a fourth honesty tier of its own: real
code, real live-verified structural safety gate, but a deliberate refusal
to ever run a live external-agent session in this environment, since the
only available sandbox backend can't isolate one — see
[`aios-architecture-and-phases.md#phase-22-external-coding-agents`](aios-architecture-and-phases.md#phase-22-external-coding-agents)
Section 7. Phase 23 (Model Router) found and fixed a real, previously
invisible bug: `default_local_model` was never actually pulled in this
environment's Ollama, and every prior phase's own live-model testing
had silently routed around it by always overriding `target_model` — see
[`aios-architecture-and-phases.md#phase-23-model-router`](aios-architecture-and-phases.md#phase-23-model-router) Section 6. Phase
24 (Control UI) is the first phase with a real browser in
the loop: `services/control-ui/` (BFF) and `web/` (Vite+React, one app
instead of the design doc's three npm packages, a documented
simplification) were live-tested end to end in an actual browser — sign
in, a chat message that created one real task, a real approval decided
and independently confirmed, real ops data. Capability views and a
settings page are the one named, out-of-scope gap — see
[`aios-architecture-and-phases.md#phase-24-control-ui-web-shell`](aios-architecture-and-phases.md#phase-24-control-ui-web-shell), `services/control-ui/README.md`,
`web/README.md`. See root [`README.md`](../README.md) status table for the
authoritative phase → service map.

**Designed, not built:** nothing — every phase in the original 24-phase
mandate is built. Real cloud-provider support for Model Router (Section
3 above) is the natural next increment when/if this system's
offline-first posture is deliberately relaxed for a specific, approved
use case.

Built-phase design docs worth re-reading before extending code:
[`aios-architecture-and-phases.md#phase-13-metrics-dashboard-health-monitor`](aios-architecture-and-phases.md#phase-13-metrics-dashboard-health-monitor),
[`aios-architecture-and-phases.md#phase-15-operations-agents`](aios-architecture-and-phases.md#phase-15-operations-agents),
[`aios-architecture-and-phases.md#phase-16-code-quality-agents`](aios-architecture-and-phases.md#phase-16-code-quality-agents),
[`aios-architecture-and-phases.md#phase-17-engineering-calculation-agents`](aios-architecture-and-phases.md#phase-17-engineering-calculation-agents),
[`aios-architecture-and-phases.md#phase-18-cross-cutting-agents`](aios-architecture-and-phases.md#phase-18-cross-cutting-agents),
[`aios-architecture-and-phases.md#phase-19-deployment-architecture-docker-deployment`](aios-architecture-and-phases.md#phase-19-deployment-architecture-docker-deployment),
[`aios-architecture-and-phases.md#phase-20-backup-strategy-disaster-recovery`](aios-architecture-and-phases.md#phase-20-backup-strategy-disaster-recovery),
[`aios-architecture-and-phases.md#phase-21-consolidated-reference`](aios-architecture-and-phases.md#phase-21-consolidated-reference),
[`aios-architecture-and-phases.md#phase-22-external-coding-agents`](aios-architecture-and-phases.md#phase-22-external-coding-agents),
[`aios-architecture-and-phases.md#phase-23-model-router`](aios-architecture-and-phases.md#phase-23-model-router),
[`aios-architecture-and-phases.md#phase-24-control-ui-web-shell`](aios-architecture-and-phases.md#phase-24-control-ui-web-shell).

---

## 5. Ideas borrowed, framework not adopted

Architectural ideas from studying ElizaOS (plugin contract, providers vs
actions, scoped memory, `composeState` / `useModel`, World/Room/Entity,
typed event bus, Web UI layering) are recorded in
[`elizaos-borrowed-ideas.md`](elizaos-borrowed-ideas.md) — **what we
actually adopt**. Optional deep-dive on the external framework itself:
[`eliza-develop-technical-reference.md`](eliza-develop-technical-reference.md)
(study only; never a runtime dependency). Capability comparison and
borrow priorities:
[`aios-vs-eliza-develop-comparison.md`](aios-vs-eliza-develop-comparison.md).
Whether the build matches the product vision / “AIOS owns workflow” NFR:
[`requirements-alignment-assessment.md`](requirements-alignment-assessment.md).
The reference checkout under `eliza-develop/` is local study material and
is gitignored — it is not imported by this Python orchestration layer.

---

## 6. How to extend

- New **service / subsystem** → follow the `add-new-service` skill;
  design doc in `docs/` first.
- New **agent capability** (Phases 16–18) → follow the
  `add-agent-capability` skill; declare `brain: erp | coding`; no new
  FastAPI service.
- External coding CLIs → Phase 22, built; `coding_agent_gateway`'s own
  structural sandbox-backend gate (Section 7 of the phase doc) is the
  reference pattern for handing any future untrusted tool a live task
  only when isolation can actually be confirmed, not assumed.
- **Control UI** → Phase 24, built; `services/control-ui/` (BFF) + `web/`
  (Vite+React) are the reference pattern for governance-first UI: chat
  submits tasks through Gateway directly, never a direct agent call; any
  mutating action the BFF touches (approvals) goes through its own
  authorize → audit → forward proxy first.

Before any implementation, follow the doc-reading protocol in
[`docs/README.md`](README.md) and `.cursor/rules/docs-reading-protocol.mdc`.

---

## Next

Every phase in the original 24-phase mandate is built. Remaining scope is
narrower increments within already-built phases: real cloud-provider
support for Model Router (a product decision, not an engineering one —
`aios-architecture-and-phases.md#phase-23-model-router` §0) and, within Control UI's own remaining
scope, a settings page (§5.6) and capability views (§5.5, blocked on a
real view-manifest convention landing on `services/extensibility/` first).
