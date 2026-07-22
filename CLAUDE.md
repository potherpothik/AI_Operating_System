# AI Operating System — Agent Instructions

This file is read by Claude Code. Cursor reads the same rules from `.cursor/rules/`
— both tools load the identical content below via import, so there is one
source of truth.

@.cursor/rules/governance-first.mdc
@.cursor/rules/service-structure.mdc
@.cursor/rules/testing-conventions.mdc
@.cursor/rules/agent-capability-schema.mdc
@.cursor/rules/docs-and-honesty.mdc
@.cursor/rules/docs-reading-protocol.mdc
@.cursor/rules/operating-discipline.mdc

## Before building

Follow `.cursor/rules/docs-reading-protocol.mdc` before implementing or
materially changing any subsystem:

1. Root `README.md` status table (built vs designed)
2. `docs/README.md` (service → phase doc map)
3. Relevant `docs/phase-N-*.md` for every service touched (including **built** phases extended via gap-fill)
4. `services/<name>/README.md` for each service
5. `docs/architecture-vision.md` when cross-cutting, new phase, or brain/routing work
6. `docs/elizaos-borrowed-ideas.md` when borrowing ElizaOS patterns
7. `docs/eliza-develop-technical-reference.md` only for optional external-framework study (never a runtime dependency)

Update phase docs **before** code when the plan changed. Never import `eliza-develop/`.

## Adding a new service or subsystem

Follow the `add-new-service` skill (`.cursor/skills/add-new-service/SKILL.md`,
also available to Claude Code at `.claude/skills/add-new-service/SKILL.md`)
for the full step-by-step workflow: read context (Step 0), design doc first,
then service scaffold, governance wiring, tests, and an honest README.

## Adding a new agent capability

A future agent-capability batch (e.g. Phase 22's coding-gateway capability) is
config, not a new FastAPI service. Follow the
`add-agent-capability` skill (`.cursor/skills/add-agent-capability/SKILL.md`,
also at `.claude/skills/add-agent-capability/SKILL.md`): `capability.yaml` +
`template.md` with `brain: erp | coding`, governance policy rules, Capability
Registry sync.
