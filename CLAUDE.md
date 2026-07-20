# AI Operating System — Agent Instructions

This file is read by Claude Code. Cursor reads the same rules from `.cursor/rules/`
— both tools load the identical content below via import, so there is one
source of truth.

Long-term vision (ERP Brain + Coding Brain, kernel map, gaps): see
`docs/architecture-vision.md` (path mentioned in backticks so it is not
auto-imported).

@.cursor/rules/governance-first.mdc
@.cursor/rules/service-structure.mdc
@.cursor/rules/testing-conventions.mdc
@.cursor/rules/agent-capability-schema.mdc
@.cursor/rules/docs-and-honesty.mdc

## Adding a new service or subsystem

Follow the `add-new-service` skill (`.cursor/skills/add-new-service/SKILL.md`,
also available to Claude Code at `.claude/skills/add-new-service/SKILL.md`)
for the full step-by-step workflow: design doc first, then service scaffold,
governance wiring, tests, and an honest README.

## Adding a new agent capability

Most Phase 15–18 work is config, not a new FastAPI service. Follow the
`add-agent-capability` skill (`.cursor/skills/add-agent-capability/SKILL.md`,
also at `.claude/skills/add-agent-capability/SKILL.md`): `capability.yaml` +
`template.md` with `brain: erp | coding`, governance policy rules, Capability
Registry sync.
