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
| Manufacturing / sales / project management | ERP | Designed (Phase 15) |
| Engineering calculations | ERP | Designed (Phase 17 `calculation_agent`) |
| Glass / fabrication / cutlist optimization | ERP | Designed (Phase 17 `cutlist_optimization_agent`) |
| Business workflows | ERP | Partial (ERP Knowledge Engine, Phase 9) |
| Databases | Shared | Built (Phase 7) |
| Django / Python | Coding | Built (Phase 10) |
| Docker / DevOps / Testing | Coding | Built (Phase 10) |
| Git repositories | Coding | Built (Phase 6 Git Manager) |
| React / frontend code quality | Coding | Designed (Phases 16–18) |
| External coding agents (OpenCode, Claude Code) | Coding | Designed (Phase 22) |

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
| Tool Router | Partial | Reasoning Engine routes `tool_call_request` (Phase 5); not a standalone module |
| Model Router | **Gap** | Ollama adapter + config overrides today; Phase 23 design seed below |

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
└── Model Router         (NOT YET — Phase 23)
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

Today: Reasoning Engine targets whatever is pulled in Ollama; model choice
is a config override (`default_local_model` / per-capability `target_model`),
not a real router. **Phase 23 (Model Router)** — not yet designed as a full
phase doc — should become a typed model-role registry (e.g. `TEXT_LARGE`,
`CODE`, `EMBEDDING`) with priority-ordered handlers, borrowing the
ElizaOS `useModel(ModelType, …)` idea without adopting that framework. See
[`elizaos-borrowed-ideas.md`](elizaos-borrowed-ideas.md).

External / cloud models remain approval-gated by Security Layer
classification rules (never send source code externally without explicit
approval).

---

## 4. Domain roadmap

**Built today:** Phases 1–12 and 14 (governance, platform spine, memory,
assembly, agents + Reasoning Engine, execution, database, planning,
knowledge pipelines, extensibility/MCP, costing/accounting/inventory).

**Designed, not built:**
- Phase 13 — Metrics Dashboard, Health Monitor
- Phase 15 — Manufacturing / sales / PM agents
- Phase 16–18 — Code-quality / engineering / cross-cutting agents
  (including `calculation_agent`, `cutlist_optimization_agent`)
- Phase 19–21 — Deployment, backup/DR, consolidated reference
  (see [`phases-12-21-remaining-subsystems.md`](phases-12-21-remaining-subsystems.md))
- **Phase 22** — External coding agents (OpenCode, Claude Code) via a
  governed Coding Agent Gateway
  ([`phase-22-external-coding-agents.md`](phase-22-external-coding-agents.md))
- **Phase 23** — Model Router (seed only; full phase doc when ready)

---

## 5. Ideas borrowed, framework not adopted

Architectural ideas from studying ElizaOS (plugin contract, providers vs
actions, scoped memory, `composeState` / `useModel`, World/Room/Entity,
typed event bus) are recorded in
[`elizaos-borrowed-ideas.md`](elizaos-borrowed-ideas.md). The reference
checkout under `eliza-develop/` is local study material and is gitignored —
it is not a dependency of this Python orchestration layer.

---

## 6. How to extend

- New **service / subsystem** → follow the `add-new-service` skill;
  design doc in `docs/` first.
- New **agent capability** (most of Phases 15–18) → follow the
  `add-agent-capability` skill; declare `brain: erp | coding`; no new
  FastAPI service.
- External coding CLIs → Phase 22 design; treat as untrusted tools under
  the same authorize → sandbox → propose → approve → merge gate.

---

## Next

Implement remaining designed agents (Phases 15–18) as config over the
shared Reasoning Engine; then Phase 22 (Coding Agent Gateway); then a full
Phase 23 Model Router doc when multi-model routing becomes a real
bottleneck rather than a config override.
