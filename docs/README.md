# Documentation index — for AI agents and contributors

This folder holds **design docs before code**. When implementing or materially
changing any subsystem, read this index first, then the phase doc(s) for every
service you touch. Full protocol: `.cursor/rules/docs-reading-protocol.mdc`.

The root [`README.md`](../README.md) status table is the authoritative
**built vs designed** list; this file adds a **service → phase doc** map and
reading order.

---

## Layer 1 — Vision (cross-cutting context)

| Doc | When to read |
|---|---|
| [`architecture-vision.md`](architecture-vision.md) | New phase, brain/routing work, kernel map, roadmap |
| [`phases-12-21-remaining-subsystems.md`](phases-12-21-remaining-subsystems.md) | Phases 12, 20–21 (consolidated designs); original design blocks for 14–19 also still live here, but each of those now has its own dedicated, built-phase doc — read the dedicated doc first |

---

## Layer 2 — Borrowed patterns (ElizaOS study, not adopted runtime)

| Doc | When to read |
|---|---|
| [`elizaos-borrowed-ideas.md`](elizaos-borrowed-ideas.md) | Borrowing plugin, memory, UI, orchestration, or model-routing *ideas* |
| [`eliza-develop-technical-reference.md`](eliza-develop-technical-reference.md) | Optional deep-dive on the external elizaOS framework (Phase 22/24, comparative design) |

**Never** import code from `eliza-develop/` (gitignored local checkout). Adopt
patterns via our Python services only. [`elizaos-borrowed-ideas.md`](elizaos-borrowed-ideas.md)
is what we actually implement; the technical reference is external study material.

---

## Layer 3 — Phase design docs (source of truth per subsystem)

| Service directory | Phase | Design doc | Built? |
|---|---|---|---|
| `services/governance/` | 1 | [`phase-1-governance-layer.md`](phase-1-governance-layer.md) | yes |
| `services/platform-spine/` | 2 | [`phase-2-gateway-task-manager-config.md`](phase-2-gateway-task-manager-config.md) | yes |
| `services/knowledge/` | 3 | [`phase-3-memory-vector-search.md`](phase-3-memory-vector-search.md) | yes |
| `services/assembly/` | 4 | [`phase-4-context-prompt-builder.md`](phase-4-context-prompt-builder.md) | yes |
| `services/agents/` (Reasoning Engine, Odoo) | 5 | [`phase-5-odoo-agent-reasoning-engine.md`](phase-5-odoo-agent-reasoning-engine.md) | yes |
| `services/execution/` | 6 | [`phase-6-shell-git-manager.md`](phase-6-shell-git-manager.md) | yes |
| `services/database/` | 7 | [`phase-7-database-connector-agent.md`](phase-7-database-connector-agent.md) | yes |
| `services/planning/` | 8 | [`phase-8-planner-capability-registry.md`](phase-8-planner-capability-registry.md) | yes |
| `services/knowledge_pipelines/` (docs + ERP knowledge) | 9 | [`phase-9-documentation-erp-knowledge-engine.md`](phase-9-documentation-erp-knowledge-engine.md) | yes |
| `services/agents/agents/{django,devops,docker,testing}_agent/` | 10 | [`phase-10-django-devops-docker-testing-agents.md`](phase-10-django-devops-docker-testing-agents.md) | yes |
| `services/knowledge_pipelines/.../code_analysis_engine/` | 11 | [`phase-11-code-analysis-engine.md`](phase-11-code-analysis-engine.md) | yes |
| `services/extensibility/` | 12 | [`phases-12-21-remaining-subsystems.md`](phases-12-21-remaining-subsystems.md) | yes |
| `services/observability/` | 13 | [`phase-13-metrics-health.md`](phase-13-metrics-health.md) | yes |
| `services/agents/agents/{costing,accounting,inventory}_agent/` | 14 | [`phases-12-21-remaining-subsystems.md`](phases-12-21-remaining-subsystems.md) | yes |
| `services/agents/agents/{manufacturing,sales,project_management}_agent/` (+ Phase 7/2 extensions) | 15 | [`phase-15-operations-agents.md`](phase-15-operations-agents.md) | yes |
| `services/agents/agents/{code_review,reverse_engineering,architecture}_agent/` (+ Phase 1 extension) | 16 | [`phase-16-code-quality-agents.md`](phase-16-code-quality-agents.md) | yes |
| `services/agents/agents/{calculation,cutlist_optimization,autocad}_agent/` (+ Phase 6/9 extensions) | 17 | [`phase-17-engineering-calculation-agents.md`](phase-17-engineering-calculation-agents.md) | yes |
| `services/agents/agents/{python,documentation,security,research}_agent/` (+ Phase 1 extension) | 18 | [`phase-18-cross-cutting-agents.md`](phase-18-cross-cutting-agents.md) | yes |
| repo root (`Dockerfile`s, `docker-compose.yml`) | 19 | [`phase-19-deployment-docker.md`](phase-19-deployment-docker.md) | yes (unbuilt/unverified — no Docker daemon in this environment) |
| backup/DR, consolidated reference | 20–21 | [`phases-12-21-remaining-subsystems.md`](phases-12-21-remaining-subsystems.md) | no |
| Coding Agent Gateway | 22 | [`phase-22-external-coding-agents.md`](phase-22-external-coding-agents.md) | no |
| Model Router (seed) | 23 | (see [`architecture-vision.md`](architecture-vision.md) §3) | no |
| `services/control-ui/` + `web/` (planned) | 24 | [`phase-24-control-ui.md`](phase-24-control-ui.md) | no |

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
7. **Plan changed?** — update the relevant `docs/phase-N-*.md` **before** code
   (see `docs-and-honesty.mdc`).

### Phase-specific mandatory reads

| Task | Also read |
|---|---|
| Phase 24 Control UI | [`phase-24-control-ui.md`](phase-24-control-ui.md), elizaos-borrowed §7, gap-fill deps: phase-2, phase-13, phase-12 |
| Phase 22 coding gateway | [`phase-22-external-coding-agents.md`](phase-22-external-coding-agents.md), elizaos-borrowed §4–5, phase-6 |
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
