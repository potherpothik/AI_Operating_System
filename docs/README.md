# Documentation index — for AI agents and contributors

This folder holds **design docs before code**. When implementing or materially
changing any subsystem, read this index first, then the phase doc(s) for every
service you touch. Full protocol: `.cursor/rules/docs-reading-protocol.mdc`.

The root [`README.md`](../README.md) status table is the authoritative
**built vs designed** list; this file adds a **service → phase doc** map and
reading order.

---

## Layer 1 — Architecture & vision

| Doc | When to read |
|---|---|
| [`installation-guide.md`](installation-guide.md) | **First-time setup** — prerequisites, Ollama, start services, Web UI |
| [`command.txt`](command.txt) | Copy-paste terminal commands (ports, curl, tests) |
| [`aios-architecture-and-phases.md`](aios-architecture-and-phases.md) | **Primary reference** — lifecycle flow, Phases 1–25 design (TOC with anchors), API/DB index (Phase 21), deployment, backup |
| [`architecture-vision.md`](architecture-vision.md) | Long-term vision, two brains, kernel map, roadmap |
| [`aios-db-erd.md`](aios-db-erd.md) | Logical database ERD across all services |
| [`aios-forward-plan-phases-25-31.md`](aios-forward-plan-phases-25-31.md) | Planning doc for Phases 25–31 — sequencing rationale, scope, what was rejected and why |

---

## Layer 2 — Borrowed patterns (ElizaOS study, not adopted runtime)

| Doc | When to read |
|---|---|
| [`elizaos-borrowed-ideas.md`](elizaos-borrowed-ideas.md) | Borrowing plugin, memory, UI, orchestration, or model-routing *ideas* |
| [`eliza-develop-technical-reference.md`](eliza-develop-technical-reference.md) | Optional deep-dive on the external elizaOS framework (Phase 22/24, comparative design) |
| [`aios-vs-eliza-develop-comparison.md`](aios-vs-eliza-develop-comparison.md) | Capability-by-capability comparison (multi-agent, memory, RAG, plugins, models, tools, REST, UI, MCP, local deploy) and what to borrow |
| [`requirements-alignment-assessment.md`](requirements-alignment-assessment.md) | Whether AIOS matches the product vision / NFR (“AIOS owns workflow; third parties are plugins”) and what to change |

**Never** import code from `eliza-develop/` (gitignored local checkout). Adopt
patterns via our Python services only. [`elizaos-borrowed-ideas.md`](elizaos-borrowed-ideas.md)
is what we actually implement; the technical reference is external study material.
The comparison and requirements docs are planning aids — they do not replace
phase design docs before implementation.

---

## Layer 3 — Phase sections (in [`aios-architecture-and-phases.md`](aios-architecture-and-phases.md))

| Service directory | Phase | Design doc | Built? |
|---|---|---|---|
| `services/governance/` | 1 | [`aios-architecture-and-phases.md#phase-1-governance-layer`](aios-architecture-and-phases.md#phase-1-governance-layer) | yes |
| `services/platform-spine/` | 2 | [`aios-architecture-and-phases.md#phase-2-platform-spine`](aios-architecture-and-phases.md#phase-2-platform-spine) | yes |
| `services/knowledge/` | 3 | [`aios-architecture-and-phases.md#phase-3-knowledge-substrate`](aios-architecture-and-phases.md#phase-3-knowledge-substrate) | yes |
| `services/assembly/` | 4 | [`aios-architecture-and-phases.md#phase-4-context-prompt-assembly`](aios-architecture-and-phases.md#phase-4-context-prompt-assembly) | yes |
| `services/agents/` (Reasoning Engine, Odoo) | 5 | [`aios-architecture-and-phases.md#phase-5-first-live-agent`](aios-architecture-and-phases.md#phase-5-first-live-agent) | yes |
| `services/execution/` | 6 | [`aios-architecture-and-phases.md#phase-6-execution-layer`](aios-architecture-and-phases.md#phase-6-execution-layer) | yes |
| `services/database/` | 7 | [`aios-architecture-and-phases.md#phase-7-data-execution-layer`](aios-architecture-and-phases.md#phase-7-data-execution-layer) | yes |
| `services/planning/` | 8 | [`aios-architecture-and-phases.md#phase-8-automatic-routing`](aios-architecture-and-phases.md#phase-8-automatic-routing) | yes |
| `services/knowledge_pipelines/` (docs + ERP knowledge) | 9 | [`aios-architecture-and-phases.md#phase-9-knowledge-ingestion`](aios-architecture-and-phases.md#phase-9-knowledge-ingestion) | yes |
| `services/agents/agents/{django,devops,docker,testing}_agent/` | 10 | [`aios-architecture-and-phases.md#phase-10-engineering-platform-agents`](aios-architecture-and-phases.md#phase-10-engineering-platform-agents) | yes |
| `services/knowledge_pipelines/.../code_analysis_engine/` | 11 | [`aios-architecture-and-phases.md#phase-11-structural-code-understanding`](aios-architecture-and-phases.md#phase-11-structural-code-understanding) | yes |
| `services/extensibility/` | 12 | [`aios-architecture-and-phases.md#ai-orchestration-layer-remaining-roadmap`](aios-architecture-and-phases.md#ai-orchestration-layer-remaining-roadmap) | yes |
| `services/observability/` | 13 | [`aios-architecture-and-phases.md#phase-13-metrics-dashboard-health-monitor`](aios-architecture-and-phases.md#phase-13-metrics-dashboard-health-monitor) | yes |
| `services/agents/agents/{costing,accounting,inventory}_agent/` | 14 | [`aios-architecture-and-phases.md#ai-orchestration-layer-remaining-roadmap`](aios-architecture-and-phases.md#ai-orchestration-layer-remaining-roadmap) | yes |
| `services/agents/agents/{manufacturing,sales,project_management}_agent/` (+ Phase 7/2 extensions) | 15 | [`aios-architecture-and-phases.md#phase-15-operations-agents`](aios-architecture-and-phases.md#phase-15-operations-agents) | yes |
| `services/agents/agents/{code_review,reverse_engineering,architecture}_agent/` (+ Phase 1 extension) | 16 | [`aios-architecture-and-phases.md#phase-16-code-quality-agents`](aios-architecture-and-phases.md#phase-16-code-quality-agents) | yes |
| `services/agents/agents/{calculation,cutlist_optimization,autocad}_agent/` (+ Phase 6/9 extensions) | 17 | [`aios-architecture-and-phases.md#phase-17-engineering-calculation-agents`](aios-architecture-and-phases.md#phase-17-engineering-calculation-agents) | yes |
| `services/agents/agents/{python,documentation,security,research}_agent/` (+ Phase 1 extension) | 18 | [`aios-architecture-and-phases.md#phase-18-cross-cutting-agents`](aios-architecture-and-phases.md#phase-18-cross-cutting-agents) | yes |
| repo root (`Dockerfile`s, `docker-compose.yml`) | 19 | [`aios-architecture-and-phases.md#phase-19-deployment-architecture-docker-deployment`](aios-architecture-and-phases.md#phase-19-deployment-architecture-docker-deployment) | yes (unbuilt/unverified — no Docker daemon in this environment) |
| `deploy/backup.sh`, `deploy/restore.sh` | 20 | [`aios-architecture-and-phases.md#phase-20-backup-strategy-disaster-recovery`](aios-architecture-and-phases.md#phase-20-backup-strategy-disaster-recovery) | yes (real, live restore drill run) |
| consolidated reference (component diagram, API/DB index) | 21 | [`aios-architecture-and-phases.md#phase-21-consolidated-reference`](aios-architecture-and-phases.md#phase-21-consolidated-reference) | yes (regenerated from grepped source, no new code) |
| `services/agents/agents/coding_agent_gateway/` (+ `coding_gateway_bridge.py`) | 22 | [`aios-architecture-and-phases.md#phase-22-external-coding-agents`](aios-architecture-and-phases.md#phase-22-external-coding-agents) | yes (live-verified safety gate; never runs a live agentic session in this environment — see Section 7) |
| `services/agents/agents/reasoning_engine/model_router.py` | 23 | [`aios-architecture-and-phases.md#phase-23-model-router`](aios-architecture-and-phases.md#phase-23-model-router) | yes (real Ollama provider + fallback, live-verified against a real dead-config bug; cloud providers real interface, honestly not_configured) |
| `services/control-ui/` + `web/` | 24 | [`aios-architecture-and-phases.md#phase-24-control-ui-web-shell`](aios-architecture-and-phases.md#phase-24-control-ui-web-shell) | yes (live-tested in a browser end to end; capability views + settings honestly out of scope) |
| `services/knowledge/` (real embeddings) | 25 | [`aios-architecture-and-phases.md#phase-25-model-retrieval-quality`](aios-architecture-and-phases.md#phase-25-model-retrieval-quality) | yes (real embedding backend swap, measured 3/3 vs 2/3 retrieval accuracy; coder-model upgrade evaluated and NOT adopted — real reliability regression found) |

Agent capabilities live under `services/agents/agents/<name>/` — read the
phase doc for that agent batch, plus [`agent-capability-schema`](../.cursor/rules/agent-capability-schema.mdc).

---

## Layer 4 — Before you code (checklist)

1. **Root README status** — confirm phase number and whether code already exists.
2. **Phase doc(s)** — read every design doc for services you will touch (including
   **built** phases you extend via gap-fill).
3. **Service README(s)** — run/test instructions and Honesty notes under
   `services/<name>/README.md`.
4. **`architecture-vision.md`** — when work is cross-cutting, a new phase, or
   affects brain/routing/kernel map.
5. **`elizaos-borrowed-ideas.md`** — when borrowing ElizaOS patterns (map section
   to task: §1 plugins, §2 agents, §3 memory, §4 tools, §5 runtime, §6 bus, §7 UI).
6. **`eliza-develop-technical-reference.md`** — optional; external framework detail
   only (never treat as this repo's source of truth).
7. **Plan changed?** — update the relevant section in
   [`aios-architecture-and-phases.md`](aios-architecture-and-phases.md) **before**
   code (see `docs-and-honesty.mdc`).

### Phase-specific mandatory reads

| Task | Also read |
|---|---|
| Phase 24 Control UI | [`aios-architecture-and-phases.md#phase-24-control-ui-web-shell`](aios-architecture-and-phases.md#phase-24-control-ui-web-shell), elizaos-borrowed §7, gap-fill deps: phase-2, phase-13, phase-12 |
| Phase 22 coding gateway | [`aios-architecture-and-phases.md#phase-22-external-coding-agents`](aios-architecture-and-phases.md#phase-22-external-coding-agents), elizaos-borrowed §4–5, phase-6 |
| Extend built service | That service's phase doc + update doc if APIs/scope change |

---

## Skills and rules

| Resource | Path |
|---|---|
| Add FastAPI service / subsystem | `.cursor/skills/add-new-service/SKILL.md` |
| Add agent capability only | `.cursor/skills/add-agent-capability/SKILL.md` |
| Doc-reading protocol (always on) | `.cursor/rules/docs-reading-protocol.mdc` |
| Governance-first | `.cursor/rules/governance-first.mdc` |
| Design doc before code | `.cursor/rules/docs-and-honesty.mdc` |

Claude Code loads the same skills from `.claude/skills/` (synced from `.cursor/skills/`).
