---
name: add-agent-capability
description: >-
  Adds a new agent capability (capability.yaml + template.md) to the shared
  Reasoning Engine in this AI Operating System repo, with brain grouping,
  governance policy rules, and Capability Registry sync. Use when the user
  asks to add a new agent, domain agent, ERP or coding brain capability,
  manufacturing/cutlist/calculation/accounting agent, or any Phase 15–18
  style capability that is config over agents — not a new FastAPI service.
---

# Add an Agent Capability

Most remaining domain work (Phases 17–18, Phase 22 gateway capability) is
**config**, not a new microservice. Use this skill instead of
`add-new-service` when the deliverable is an agent under
`services/agents/agents/`.

## Workflow

Copy this checklist and work through it in order:

```
- [ ] 0. Read context (docs/README.md, phase docs for built deps, service READMEs)
- [ ] 1. Confirm design doc / capability block exists in docs/
- [ ] 2. Create services/agents/agents/<name>/ with capability.yaml + template.md
- [ ] 3. Add governance policy rules and reload
- [ ] 4. Register / sync Capability Registry + Planner
- [ ] 5. Write or extend tests
- [ ] 6. Honesty notes + root README status if needed
```

### 0. Read context

Follow `.cursor/rules/docs-reading-protocol.mdc` and [`docs/README.md`](../../../docs/README.md):

- Phase doc for the **new capability** (consolidated or dedicated)
- Phase docs for **built services** the capability will call (governance Phase 1, execution Phase 6, database Phase 7, etc.)
- [`docs/architecture-vision.md`](../../../docs/architecture-vision.md) for brain/routing context

### 1. Confirm design coverage

- Prefer an existing design block in `docs/phases-12-21-remaining-subsystems.md`
  or a dedicated phase doc (e.g. Phase 22) before inventing a capability.
- If none exists, write or extend the design doc first (same skeleton as
  other phase docs: responsibilities, allowed/forbidden actions, approval
  gates, out of scope).

### 2. Scaffold the capability

```
services/agents/agents/<snake_case>_agent/
├── capability.yaml
└── template.md
```

`capability.yaml` shape (see `agent-capability-schema.mdc`):

```yaml
capability: <snake_case>_agent
brain: erp | coding
allowed_actions: [...]
forbidden_actions: [...]    # deny-by-default; "*" catch-all OK
requires_approval: [...]
classification_ceiling: internal | confidential | ...
known_limitation: <optional>
```

- `brain: erp` — Odoo, accounting, inventory, manufacturing, calculations, cutlist/glass, projects.
- `brain: coding` — Django, DevOps, Docker, testing, code review, Coding Agent Gateway.
- Roster stays **flat** (no `erp/` vs `coding/` directories).

`template.md` must instruct the model to emit the shared 6-field schema
(`reasoning`, `answer_or_proposal`, `confidence`, `provenance`,
`risk_classification`, `delegate_to`). Stay inside `allowed_actions`; set
`delegate_to` for out-of-scope work; never treat approval-required actions
as done until a human approves.

Routing-only capabilities (Planner-style) need structural overrides in
Reasoning Engine — do not rely on prompt wording alone for
`delegate_to` / `risk_classification` semantics.

### 3. Wire governance

- Add policy rules under governance `policies/*.yaml` for the new
  `domain.verb` actions and the agent role.
- Call `POST /security/reload` after policy changes.
- Mutating actions must go authorize → (dry-run/preview) → approval →
  execute; never direct execute.

### 4. Register and sync

- Ensure the agents service exposes the capability (same discovery path as
  existing agents — typically filesystem under `agents/agents/`).
- Sync Planner's live roster: `POST /capabilities/sync` on the planning
  service (see root `README.md` / `services/planning/`).
- Confirm the new capability appears in `GET /capabilities` (or equivalent)
  before claiming it is routable.

### 5. Tests

- Prefer pytest coverage that loads the capability declaration and exercises
  schema validation / routing refuse paths, matching existing agent tests.
- If the capability calls execution or database, test the governed propose
  path — not a bypass.
- Against real Postgres / Ollama when the path touches them; do not fake
  success when a dependency is missing (`not_configured` is correct).

### 6. Honesty notes and status

- If the capability is stubbed or only partially verified, say so in
  `services/agents/README.md` (and root README Honesty notes when material).
- Update the root `README.md` status table when a whole phase's agents land.

## Related

- New FastAPI service instead? → `add-new-service` skill.
- Doc index + read order → [`docs/README.md`](../../../docs/README.md).
- Vision / brain map → [`docs/architecture-vision.md`](../../../docs/architecture-vision.md).
- ElizaOS borrowed patterns → [`docs/elizaos-borrowed-ideas.md`](../../../docs/elizaos-borrowed-ideas.md).
- External OpenCode / Claude Code wrapper → [`docs/phase-22-external-coding-agents.md`](../../../docs/phase-22-external-coding-agents.md).
- Control UI (not an agent capability) → [`docs/phase-24-control-ui.md`](../../../docs/phase-24-control-ui.md) + `add-new-service`.
