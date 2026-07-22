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
| MCP Surface (AIOS exposed TO IDEs) | Built | Phase 26 → `services/mcp-surface/` |
| OpenAI-Compatible Endpoint (the GPU-day switch) | Built | Phase 27 → `services/platform-spine/platform_spine/gateway/openai_shim.py` |
| Tool Router | Partial | Reasoning Engine routes `tool_call_request` (Phase 5); not a standalone module |
| Model Router | Built | Phase 23 → `services/agents/agents/reasoning_engine/model_router.py` — real typed registry + Ollama fallback; cloud providers real interface, honestly not_configured |
| Identity Provider (real per-user auth) | Built | Phase 31 → `services/identity/` — real self-hosted OIDC; `AUTH_MODE=oidc` wired into Gateway, the OpenAI shim, Control UI (MCP Surface's own wiring honestly deferred) |

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
├── Model Router         (reasoning_engine/model_router.py — Phase 23)
├── MCP Surface          (mcp-surface — Phase 26, AIOS exposed TO IDEs)
├── OpenAI Shim          (platform_spine/gateway/openai_shim.py — Phase 27, the GPU-day switch)
└── Identity Provider    (identity — Phase 31, real self-hosted OIDC)
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

**Built today:** every phase in the original mandate, 1–24, plus Phases
25–29 from the new Phases 25–31 forward plan (governance,
platform spine, memory,
assembly, agents + Reasoning Engine, execution, database, planning,
knowledge pipelines, extensibility/MCP, observability metrics/health,
costing/accounting/inventory agents, manufacturing/sales/PM agents,
code-review/reverse-engineering/architecture agents, calculation/cutlist-
optimization/AutoCAD agents, python/documentation/security/research agents,
Coding Agent Gateway, Model Router, Control UI, MCP Surface, OpenAI-
Compatible Endpoint, Adapter Contracts, Tool Adapter Gaps), plus
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
`web/README.md`. Phase 25 (Model & Retrieval Quality) adopted real
semantic embeddings (`nomic-embed-text`) after measuring 3/3 vs 2/3
correct top-1 retrieval against real ERP-domain paraphrase queries — and
found a real silent-corruption bug along the way (a dimension mismatch
after switching backends, now a clean `409` instead of a wrong answer).
It evaluated `qwen2.5-coder:7b` as a default-model upgrade and
deliberately did **not** adopt it: better raw code, but reproducibly less
reliable at this system's structured-output contract when run through the
real agent pipeline twice — see
[`aios-architecture-and-phases.md#phase-25-model-retrieval-quality`](aios-architecture-and-phases.md#phase-25-model-retrieval-quality).
Phase 26 (MCP Surface) added a new, twelfth backend service
(`services/mcp-surface/`) — a real MCP JSON-RPC server exposing 8
governed tools to any MCP-speaking IDE, with no tool anywhere able to
decide a pending approval — and wired Phase 12's existing MCP client
into Reasoning Engine as a real tool source for `research_agent`,
live-tested end to end. It also found and fixed two real, previously
latent bugs in `services/assembly/`'s prompt-template versioning (a
body-diff gap and a string-vs-numeric version-ordering bug) — see
[`aios-architecture-and-phases.md#phase-26-mcp-surface`](aios-architecture-and-phases.md#phase-26-mcp-surface).
Phase 27 (OpenAI-Compatible Endpoint) added the "GPU-day switch": real
`POST /v1/chat/completions` (live SSE streaming, token-by-token,
confirmed via `curl -N`) and `GET /v1/models` on the Gateway
(`services/platform-spine/platform_spine/gateway/openai_shim.py`), with
a real, live-verified structural bar — content classified above a
candidate model's real ceiling never reaches the model at all, both
allow and deny decisions provable in the real audit trail. It found and
fixed a second real bug hiding behind Phase 23's already-known dead
config value: the same stale `default_local_model` was silently giving
the actual local model (`qwen3.5:4b`) a `public` classification ceiling
instead of `confidential`, refusing a benign request live for the wrong
reason — corrected at the source this time — see
[`aios-architecture-and-phases.md#phase-27-openai-compatible-endpoint`](aios-architecture-and-phases.md#phase-27-openai-compatible-endpoint).
Phase 28 (Adapter Contracts) adds no new service — three versioned
interface contracts (`ModelProvider`, `ToolAdapter`, `IDESurface`) in
[`docs/contracts/`](contracts/), extracted from Phases 23/26/27's real
implementations, plus real, static enforcement of "agents may not make
bespoke third-party calls": `services/agents/tests/test_adapter_boundary.py`
AST-scans for it, live-verified to actually catch a violation, and
found one real pre-existing exception (`planner_bridge.py` bypassing
`agents/clients.py`) on its first run — see
[`aios-architecture-and-phases.md#phase-28-adapter-contracts`](aios-architecture-and-phases.md#phase-28-adapter-contracts).
Phase 29 (Tool Adapter Gaps) adds three new `ToolAdapter`s under those
contracts, each at a genuinely different honesty tier: a live Odoo
XML-RPC adapter (real code, no live Odoo 19 instance exists here to
verify a successful query against), a Django `manage.py` adapter (fully
real and live-tested against a genuine disposable Django project), and a
Playwright browser adapter (real code, its structural internal-only URL
gate fully verified, but real page loads currently refused by this
environment's own sandboxed-subprocess memory limit — the same class of
finding Phase 22 already established for external coding-agent CLIs
under this identical sandbox, confirmed by direct reproduction, never
worked around by weakening the sandbox) — see
[`aios-architecture-and-phases.md#phase-29-tool-adapter-gaps`](aios-architecture-and-phases.md#phase-29-tool-adapter-gaps).
Phase 30 (Declarative Workflows) adds `services/planning/planning/workflows/` —
saved, re-triggerable multi-agent flows as YAML data
([`workflows/code_review_pipeline.yaml`](../workflows/code_review_pipeline.yaml)),
deliberately reusing Phase 8's own `TaskGraph`/`Subtask` schema rather
than inventing a second graph model. Before writing any dispatch code,
an exhaustive grep across the whole codebase confirmed a real,
previously-undocumented architectural fact: this system has never had a
background task or approval dispatcher anywhere in 29 prior phases —
Task Manager's `dequeue()` has zero callers, and Control UI's own
approval decision never resumes a paused execution. Workflow dispatch
and continuation are therefore built as explicit calls
(`dispatch_ready_subtasks()`, `advance()`), matching Reasoning Engine's
own `resume()` philosophy rather than adding this project's first
scheduler. A workflow batches orchestration, never consent — each
step's own governance gate is exactly the same one a non-workflow call
to that capability already needs. MCP Surface gained a 9th tool,
`trigger_workflow` — see
[`aios-architecture-and-phases.md#phase-30-declarative-workflows`](aios-architecture-and-phases.md#phase-30-declarative-workflows).
Phase 31 (Team & GPU-Day Hardening), the final phase in the forward
plan, adds `services/identity/` — a new, real, hand-built self-hosted
OIDC provider (real RSA-signed JWTs, real bcrypt users, real single-use
authorization codes, not a mock and not a third-party dependency).
`AUTH_MODE=oidc` is additive — default stays `stub`, so nothing built
across the prior 30 phases breaks — and wires real per-user identity
into Gateway, the OpenAI-compatible endpoint, and Control UI through
governance's new token-aware `/security/authorize` (verifies the token
itself, authorizes by its real `role` claim, records its real `sub` as
the audit actor). Confirmed live both ways: a real OIDC task's
`requested_by` and a real OIDC approval's `decided_by` both show the
real per-user identity. `ENFORCE_APPROVER_NOT_REQUESTER` makes
self-approval rejection real once distinct users exist. A
docker-compose review found a real, pre-existing gap — `mcp-surface`
(26) and `control-ui`/`web` (24) had no Dockerfile or compose entry at
all — fixed in passing. MCP Surface's own per-request OIDC wiring is
honestly named as remaining work, not silently skipped: the `mcp` SDK's
request-context access needs its own careful, tested pass. See
[`aios-architecture-and-phases.md#phase-31-team-and-gpu-day-hardening`](aios-architecture-and-phases.md#phase-31-team-and-gpu-day-hardening).

Two small phases followed the forward plan's own final phase, both real
gaps found by checking actual code rather than assuming from a file
listing. Phase 32 (Schema Drift Detection) closed a genuine gap found
while correcting a stray, uncommitted `docs/ARCHITECTURE_PLAN.md` draft
that had proposed a redundant `services/orchestrator/` on the false
premise that no orchestration core existed (it does — Planner,
Reasoning Engine, governance, and Phase 30's workflows already are
that core; the file was rewritten instead of the service being built).
`services/knowledge_pipelines/knowledge_pipelines/erp_knowledge_engine/drift.py`
now does a real structured table/column diff against the stored ERP
schema snapshot (`GET .../drift`, `POST .../check-and-sync`) — explicit
and on-demand, same "never a background daemon" posture as every other
part of this system. Phase 33 (Operating Discipline) applied a
user-supplied operating manual to two genuinely different audiences at
two genuinely different token budgets:
`.cursor/rules/operating-discipline.mdc` (near-verbatim, governs Claude
Code/Cursor working on this repo) and a short, distilled addendum to
`services/assembly/`'s one shared prompt fragment every one of 25+
agents already embeds (`{shared_fragment}`) — reaching every agent's
rendered prompt with zero per-agent template edits, deliberately kept
short rather than transplanting the full manual, since Phase 25 already
found that verbose prompting hurts this system's local model's
structured-output reliability, not helps it. See
[`aios-architecture-and-phases.md#phase-32-schema-drift-detection`](aios-architecture-and-phases.md#phase-32-schema-drift-detection)
and
[`aios-architecture-and-phases.md#phase-33-operating-discipline`](aios-architecture-and-phases.md#phase-33-operating-discipline).

See root [`README.md`](../README.md) status table for the
authoritative phase → service map.

**All 33 phases in the original + forward plan, plus two real gaps found
after it, are now built.** Real
cloud-provider support for Model Router remains a product decision, not
an engineering one, independent of that sequence — see Phase 23 §0.

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
[`aios-architecture-and-phases.md#phase-24-control-ui-web-shell`](aios-architecture-and-phases.md#phase-24-control-ui-web-shell),
[`aios-architecture-and-phases.md#phase-25-model-retrieval-quality`](aios-architecture-and-phases.md#phase-25-model-retrieval-quality).

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

All 31 phases in the forward plan's own sequencing are built (the
plan itself is merged into `aios-architecture-and-phases.md`'s own
"Forward Plan" section, above Phase 25), plus two further phases outside
that plan: Phase 32 (Schema Drift Detection) and Phase 33 (Operating
Discipline), both real gaps found and closed after the forward plan's
own final phase — see the narrative above. What remains is a set of
real, individually-named gaps within already-built phases, not a queued
next phase:

- **MCP Surface's own per-request OIDC wiring** (Phase 31) — the `mcp`
  SDK's request-context access needs its own careful, tested pass; its
  fixed stub actor from Phase 26 is unchanged for now.
- A real workflow-runs view in `web/`, and wiring Control UI's approval
  decision to auto-advance a paused workflow step (both named honestly
  as gaps in Phase 30 — `aios-architecture-and-phases.md#phase-30-declarative-workflows`
  — rather than assumed away).
- A real Odoo 19 instance to test `odoo_live_bridge.py`'s success path
  against, and a Docker sandbox backend to unblock `browser_bridge.py`'s
  real page loads (Phase 29).
- Real cloud-provider support for Model Router — a product decision,
  not an engineering one (`aios-architecture-and-phases.md#phase-23-model-router`
  §0).
- Whether `qwen2.5-coder:7b`'s structured-output reliability gap is
  fixable for the AGENTIC pipeline specifically
  (`aios-architecture-and-phases.md#phase-25-model-retrieval-quality`
  §2 — it's already live as Phase 27's real chat-completions fallback,
  where that gap doesn't apply).
- Within Control UI's own remaining scope: a settings page (§5.6) and
  capability views (§5.5, blocked on a real view-manifest convention
  landing on `services/extensibility/` first).
- The GPU-day playbook itself (`docs/gpu-day-playbook.md`) is real and
  traceable to existing code, but genuinely unrehearsed against a real
  GPU — none exists in this environment.
