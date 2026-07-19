# Phase 8 — Automatic Routing
### Planner · Capability Registry

---

## 0. Priority Decision: Why This Phase Is Eighth

**Why it exists here:** with two working agents proven (Odoo Agent, Phase 5; Database Agent, Phase 7) and the propose → approve → execute pattern validated across both code and data, hardcoding "which agent handles this task" as a given input — true since Phase 2 — has become the actual bottleneck rather than a reasonable simplification. Planner and Capability Registry are paired because Planner's core job — deciding how to route and decompose a task — is meaningless without a trustworthy, live index of what agents actually exist and what they're scoped to do. Building Planner against a hardcoded or scattered capability list would just move the "given input" problem down one layer instead of solving it.

**Alternatives considered**
- *Build Planner earlier, right after Phase 5's first agent* — correctly deferred, in retrospect. With only one agent, "planning" reduces to "always pick Odoo Agent," which validates nothing about real routing or decomposition. Two differently-scoped agents — Odoo Agent's ERP domain vs. Database Agent's cross-cutting data mechanics — is the minimum needed to design a Planner against a real choice.
- *Keep capability declarations scattered per-agent, as they've been since Phase 5* — rejected. Planner's job requires searching and filtering across capabilities, an access pattern scattered YAML files don't support well. A registry is a small module, but a real one, not a rename of what already existed.
- *Give Planner unrestricted visibility into all capabilities' full context regardless of classification, since "it's deciding, not executing"* — rejected. Planner still reads real task content to decompose it well, so it needs its own classification discipline. Resolved by having Planner reason at the requesting human's own classification level — the same access a human reading the task themselves would have — while each subtask's actual execution independently re-derives its own ceiling through Context Builder (Phase 4). Planner's broader planning-time visibility never bypasses per-agent enforcement at execution time.

**Trade-offs:** adds a reasoning hop, and real inference latency, before any task reaches an agent — a task now costs at least two model calls (plan, then execute) instead of one. Accepted, because the alternative is a human manually assigning `agent_capability` to every task forever, which is exactly the manual bottleneck an AI operating system is supposed to remove.

**Security implications:** Planner is the first module whose mistakes are routing mistakes rather than execution mistakes. Sending a subtask to a poor-fit capability is lower stakes than a bad DB write, but a systematically wrong plan could repeatedly probe agents outside their intended scope. The backstop is the "know when to refuse" behavior already built into every agent since Phase 5 — not a new mechanism.

**Performance implications:** adds a planning hop to every task's latency. A concrete future optimization — not committed to in this phase — is routing planning itself to a smaller, faster local model, since decomposition is a narrower, more structured task than open-ended domain reasoning.

**Future scalability:** a live capability registry is what makes the mandate's full 20+-agent roster actually tractable for Planner to reason over — without it, Planner's own prompt would need to hardcode a growing agent list, the exact anti-pattern avoided everywhere else in this design.

**Estimated complexity:** Medium. Planner reuses Reasoning Engine, Context Builder, and Prompt Builder entirely — no new execution infrastructure. The real new work is the task-graph output schema, re-planning logic, and the registry's query surface.

---

## 1. Planner

**Responsibilities**
- Takes a raw task from Task Manager and decides which agent capability (or capabilities) should handle it, whether it needs to be split into subtasks, and what dependency order those subtasks run in
- Runs through the existing Reasoning Engine (Phase 5) with its own capability (`planner`) and its own output contract — a task graph, not a single answer — the same "configuration over shared infrastructure" pattern every agent since Phase 5 has followed
- Queries the live Capability Registry rather than reasoning over a hardcoded agent list
- Produces a task graph: subtasks tagged with `agent_capability`, with explicit `depends_on` relationships
- Detects when *no* existing capability covers a task, or part of one, and surfaces that as a first-class outcome rather than forcing an ill-fitting agent to attempt it — the same triage every individual agent already does, one level up, before a task is routed to any single agent
- Handles re-planning: when a subtask comes back `refused`, or `delegate_request` names a capability that doesn't exist, or a downstream approval is rejected, Planner decides whether to produce a revised graph or surface the failure to the human
- Flags genuine ambiguity in the incoming task as `needs_clarification` rather than guessing a decomposition and burning agent and approval cycles on a bad guess

**Inputs:** `{task_id, title, description, requested_by, context_refs}`, plus a live read of the capability registry

**Outputs:** `{task_graph: [{subtask_id, description, agent_capability, depends_on[], status}], planning_confidence, needs_clarification, clarification_question?}`

**APIs**

| Endpoint | Purpose |
|---|---|
| `POST /planner/plan` | Task → task graph |
| `POST /planner/replan` | Task_id + failure/rejection reason → revised task graph |
| `GET /planner/capabilities` | Introspect the capability set Planner is reasoning over — useful for debugging routing decisions |

**Failure handling:** if no valid decomposition exists (the task is out of scope for the whole system, not just one agent), Planner returns `no_capability_found` rather than forcing a bad-fit assignment. If the Capability Registry itself is unreachable, Planner fails closed — no plan is produced — rather than routing against a stale cached registry that could send a task to a capability whose scope has since changed.

**Logging:** every plan and re-plan is logged as its own reasoning trace (inherited automatically from running through Reasoning Engine), and the resulting task graph is persisted so "why was this task structured this way" is always answerable.

**Security:** Planner reasons at the requesting human's own classification level to plan well, but never hands that broader visibility downstream — each subtask's actual execution re-derives its own ceiling independently through Context Builder when it actually runs. Planner's visibility is a separate, earlier checkpoint, not a bypass of Phase 4's enforcement.

**Future extension points:** cost/latency-aware planning (routing planning itself to a cheaper model where task complexity allows); learned planning quality, using how often a graph needed re-planning as a signal to improve future decomposition; true parallel execution of independent subtask branches, rather than today's effectively sequential dependency walk.

---

## 2. Capability Registry

**Responsibilities**
- Single source of truth for which agent capabilities currently exist — aggregates every agent's `capability.yaml` (introduced per-agent since Phase 5) into one queryable index, rather than each consumer reading scattered files independently
- Versioned: a capability's scope changing is itself a security-relevant event and routes through the same approval gate as Phase 2's security-tagged config changes
- Supports the query patterns Planner actually needs — "which capabilities can handle action type X," "which are cleared for classification Y" — not just single-capability lookup by name

**Inputs:** capability declarations, loaded at startup or on registration; queries from Planner, Reasoning Engine, Security Layer

**Outputs:** capability records; filtered/searchable query results

**APIs**

| Endpoint | Purpose |
|---|---|
| `GET /capabilities` | List all, filterable by action type, classification ceiling, status |
| `GET /capabilities/{id}` | Single capability detail |
| `POST /capabilities/register` | Register a new capability — approval-gated |
| `POST /capabilities/{id}/deprecate` | Retire a capability |

**Failure handling:** fail closed — if the registry is unreachable, Planner cannot plan; an explicit "planning unavailable" beats routing against a stale in-memory guess. Registration requests that fail validation (missing fields, contradictory allow/forbid rules) are rejected outright, never partially applied.

**Logging:** every registration, deprecation, and scope change logged to Audit Logger — effectively the audit trail of what the system could do, and when it changed.

**Security:** registry entries are the actual source of truth Security Layer's own capability-level policy checks reference, so the registry needs the same integrity guarantees as Security Layer's policy files themselves — version-controlled, branch-protected, approval-gated changes.

**Future extension points:** capability health/success-rate tracking, feeding Planner's learned-quality extension point; a capability marketplace once Plugin System (future phase) exists, so third-party capabilities register through the same path as built-in ones.

---

## 3. How the Two Interact

```
Human submits a task via Gateway → Task Manager.enqueue()                     [Phase 2]
        │
        ▼
Planner.plan(task) — runs via Reasoning Engine / Context Builder / Prompt Builder, capability='planner'
        │
        ├── Capability Registry.query(...) — what exists, action types, ceilings
        ├── Context Builder assembles context at the requesting human's classification level  [Phase 4]
        └── → task_graph, or needs_clarification
        │
        ├── needs_clarification=true ──► Task Manager: status=needs_clarification, surfaced to human
        │
        └── task_graph produced
                ▼
        Task Manager: creates subtasks, tracks depends_on
                ▼
        For each subtask, in dependency order:
                Context Builder.build(subtask, assigned agent_capability, ...)   [Phase 4 — own ceiling, re-derived]
                        ▼
                Reasoning Engine.execute(...)                                     [Phase 5]
                        ├── refused / delegate_request naming an unplanned capability
                        │        └──► Planner.replan(task_id, reason)
                        └── completed ──► Task Manager: subtask done, unblocks dependents
```

---

## 4. Minimal Data Model for This Phase

```sql
task_graph (
  id, task_id, planning_confidence, needs_clarification,
  clarification_question, created_at, superseded_by
)
subtask (
  id, task_graph_id, description, agent_capability, depends_on[], status
)

capability_registry_entry (
  id, agent_capability, version, allowed_actions[], forbidden_actions[],
  requires_approval[], classification_ceiling, status, registered_at, deprecated_at
)
```

---

## 5. Folder Structure for This Phase

```
planning/
├── planner/
│   ├── api.py
│   ├── template.md               # registered into Prompt Builder, capability='planner'
│   ├── graph_builder.py            # task → task_graph
│   └── replan.py                    # handles refusal/delegate/rejection feedback
└── capability_registry/
    ├── api.py
    ├── loader.py                   # aggregates capability.yaml from each agent
    └── store.py
```

---

## 6. Explicitly Out of Scope for This Phase

No parallel subtask execution scheduling — Task Manager still walks the dependency graph effectively sequentially. No cost/latency-aware model selection specifically for planning (noted future extension). No Plugin System integration for third-party capability registration (future phase).

---

## Next

Phase 9: Documentation Engine + ERP Knowledge Engine — the domain-specific content pipelines deferred since Phase 3. Every agent built so far, and Planner itself, has been reasoning over placeholder cached schema and business memory rather than real ingested documentation. Feeding Vector Search properly matters more at this point than adding another agent that would face the same knowledge gap.
