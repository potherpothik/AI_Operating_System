# Phase 10 — Engineering-Platform Agents
### Django Agent · DevOps Agent · Docker Agent · Testing Agent

---

## 0. Priority Decision: Why This Phase Is Tenth, and Why Batched

**Why it exists here:** Phase 9 fixed the knowledge-starvation problem; Odoo Agent, Database Agent, and Planner (Phases 5, 7, 8) already proved the routing/execution pattern works. The next highest-leverage move is applying that now-proven, now-resourced pattern to widen coverage — not inventing more shared infrastructure the system has no evidence it needs yet.

**Why four agents at once, breaking the one-or-two-modules-per-phase pattern used through Phase 9:** the marginal cost of the *next* agent is now genuinely small — a `capability.yaml` and a `template.md` per Phase 5/8's design, no new infrastructure. Batching is the more honest reflection of that reality; doing this four more times as separate phases would mostly repeat the same shared-infrastructure justification already made in Phases 4–8.

**Why these four specifically:** Django Agent — the other named platform in the stack, alongside Odoo. DevOps Agent and Docker Agent as a natural pair, since Docker is core to the deployment story and the two have a real boundary worth defining explicitly. Testing Agent, because it has immediate value against everything already built — validating Odoo Agent's and Django Agent's proposals before a human spends review time on them — not just against future agents.

**Alternatives considered**
- *Build the business agents (Costing, Inventory, Accounting, ...) next instead* — closer to the mandate's actual ERP business value, and the right call soon, but rejected for this specific phase. Engineering-platform agents are lower-risk to stress-test the batched-agent pattern with: a mistake in a DevOps Agent CI proposal is more contained than a mistake in an Accounting Agent costing proposal.
- *Build Code Analysis Engine first, since Django Agent is bottlenecked without it* — a fair point, addressed below as an explicit, named limitation on Django Agent rather than a blocker. Django Agent still has real value from documentation-level understanding alone, the same way Odoo Agent shipped in Phase 5 without live DB access and was still useful.
- *Keep one agent per phase* — rejected here specifically. The shift to batching is itself the decision worth explaining, not something to execute silently once the pattern is proven.

**Trade-offs:** less individual design scrutiny per agent than Odoo Agent or Database Agent received. Accepted because these four are lower-stakes by construction (mostly propose-only; deployment execution explicitly deferred; test execution structurally confined to sandboxed environments), and the shared baseline they all inherit already received full scrutiny in Phases 4–8.

**Security implications:** with six agents now active, the real novel risk isn't any single agent's capability list — it's a badly drawn boundary between agents: two willing to attempt the same task, or a gap neither will cover. The delegate-boundary matrix (Section 6) is this phase's actual security surface.

**Performance implications:** none beyond what Phases 5–8 already established — more Reasoning Engine executions and Planner decisions, no new latency shape.

**Future scalability:** this phase is itself the template for how the next batch (business agents) should be sequenced — state the shared baseline once, then diff each agent against it.

**Estimated complexity:** Medium, front-loaded into judgment calls (drawing the delegate boundaries correctly) rather than new infrastructure — no new modules are introduced this phase, only new capability declarations and templates.

---

## 1. What Every Agent in This Phase Inherits (stated once, not per agent)

- Runs through the shared Reasoning Engine (Phase 5) via a `capability.yaml` and `template.md` — no agent-specific API of its own
- Structured output per Prompt Builder's schema: `reasoning, answer_or_proposal, confidence, provenance[], risk_classification, delegate_to?`
- Any mutating action requires dry-run/preview plus Human Approval Layer, executed via Git Manager (Phase 6) for code or Database Connector (Phase 7) for data — never direct execution
- Registered in Capability Registry (Phase 8) — **Planner requires zero code changes to route to any of these four**, since it was built to query the registry generically rather than hardcode agents
- Draws on Documentation Engine and ERP Knowledge Engine content (Phase 9) via Vector Search
- Logged identically: Reasoning Engine trace + agent-level outcome + the relevant execution-layer log

---

## 2. Django Agent

**Capability**
```
capability: django_agent
allowed_actions:   [django.explain_structure, django.propose_migration, django.propose_config_change]
forbidden_actions: [django.direct_deploy, django.write_migration_direct, *]
requires_approval: [django.propose_migration, django.propose_config_change]
classification_ceiling: internal
known_limitation: no deep source-code analysis until Code Analysis Engine exists
```

**Distinctive scope:** explains Django app structure, URL routing, and views at the level Documentation Engine's ingested docs support — not by reading the live codebase in depth, since Code Analysis Engine doesn't exist yet. `django.propose_migration` routes through the same `migration_adapter/django.py` path already stubbed in Phase 7's Database Connector folder structure. Is explicit in its own output when a question would need real source-code understanding it doesn't have, rather than guessing past that limit.

**Refuses:** deep refactoring proposals beyond documentation-level understanding. **Delegates:** schema questions → Database Agent; deployment questions → DevOps Agent.

---

## 3. DevOps Agent

**Capability**
```
capability: devops_agent
allowed_actions:   [devops.explain_topology, devops.propose_pipeline_change, devops.propose_infra_change]
forbidden_actions: [devops.execute_deploy, devops.direct_infra_change, *]
requires_approval: [devops.propose_pipeline_change, devops.propose_infra_change]
classification_ceiling: internal
known_limitation: no deployment execution until a dedicated future phase, mirroring how database writes got their own phase
```

**Distinctive scope:** explains deployment architecture from ingested architecture docs, proposes CI/CD and infra-as-code changes as a Git Manager MR — same propose-only pattern as every other agent. Deployment *execution* is deliberately out of scope here, for the same reason DB write execution got its own dedicated Phase 7 rather than riding along with Phase 6: the blast radius of a live deploy warrants dedicated design attention, not a bundled afterthought.

**Refuses:** any direct production deployment or infra mutation. **Delegates:** container-specific detail → Docker Agent; test-pipeline specifics → Testing Agent.

---

## 4. Docker Agent

**Capability**
```
capability: docker_agent
allowed_actions:   [docker.inspect (read-only, via Shell Executor), docker.propose_compose_change]
forbidden_actions: [docker.exec_into_container, docker.stop_prod, docker.rm, *]
requires_approval: [docker.propose_compose_change]
classification_ceiling: internal
```

**Distinctive scope:** the first agent in this phase with a genuine, low-risk read-only Shell Executor use case — `docker ps` / `docker logs` style inspection runs in read-only mode, no approval needed, per Phase 6's read-only bypass rule. Dockerfile and compose-file changes are ingested by Documentation Engine (compose YAML is already a document-shaped source it can parse) and proposed as Git Manager MRs like any other change.

**Refuses:** `docker exec` into a running container to hotfix something live — exactly the kind of untracked, undocumented change the provenance/audit design throughout this project exists to prevent; any direct stop/remove of a production container. **Delegates:** broader pipeline/infra questions → DevOps Agent; "what app is actually running in this container" → Django Agent or Odoo Agent, depending on which app.

---

## 5. Testing Agent

**Capability**
```
capability: testing_agent
allowed_actions:   [testing.run_suite (test-environment only), testing.propose_new_test, testing.report_coverage]
forbidden_actions: [testing.run_against_prod, testing.direct_ci_change, *]
requires_approval: [testing.propose_new_test]
classification_ceiling: internal
environment_constraint: execution target MUST resolve to a designated test/sandbox environment; Security Layer verifies before every run
```

**Distinctive scope:** the first agent whose core value is *executing* something (a test suite) rather than only proposing. `testing.run_suite` doesn't require approval, since it's read-only against a sandbox with no real-world mutating effect — but it introduces a genuinely new safety question the other five agents haven't needed: not just *what classification is this content*, but *which environment does this even point at*. Security Layer verifies the resolved connection target is a sandbox before every run, structurally, not by policy convention alone — the same fail-closed discipline Database Connector applies to credentials in Phase 7.

**Refuses:** running the suite against anything that resolves to production; modifying CI configuration directly. **Delegates:** an actual code fix for a failing test, beyond the test file itself → whichever agent owns that code; CI pipeline changes → DevOps Agent.

---

## 6. Delegate Boundaries Across All Six Agents

```
Task concerns...                             → Routes to
──────────────────────────────────────────────────────────────
Odoo business logic, ORM, modules             → Odoo Agent
Raw SQL / cross-cutting data mechanics         → Database Agent
Django app structure, URLs, views               → Django Agent
CI/CD pipeline, infra-as-code, deployment        → DevOps Agent
Dockerfiles, compose, container state             → Docker Agent
Test authorship, coverage, test execution          → Testing Agent

Cross-agent handoffs (delegate_request):
  Django Agent   → schema questions              → Database Agent
  Django Agent   → deployment questions            → DevOps Agent
  DevOps Agent   → container-specific detail         → Docker Agent
  DevOps Agent   → test-pipeline specifics             → Testing Agent
  Docker Agent   → broader infra/pipeline                → DevOps Agent
  Docker Agent   → "what app is this running"              → Django Agent / Odoo Agent
  Testing Agent  → code fix beyond the test itself           → whichever agent owns that code
  Testing Agent  → CI pipeline changes                          → DevOps Agent
  Odoo Agent     → raw DB mechanics                                → Database Agent
  Database Agent → business meaning of the data                       → Odoo Agent
```

This matrix is documentation for human review, not a hard dependency for Planner — Planner already routes off action-type and classification ceiling per Phase 8, so a badly-drawn boundary shows up as unnecessary `delegate_request` round-trips rather than a hard failure. Worth watching in practice, not just designing correctly on paper.

---

## 7. Data Model for This Phase

```sql
-- all four capabilities reuse capability_registry_entry (Phase 8) — no new table required

-- optional enrichment for human review and Planner's future learned-routing quality signal (Phase 8)
delegate_boundary (
  id, from_capability, to_capability, condition_description
)

-- Testing Agent's environment-target verification
test_execution_target (
  id, capability, resolved_environment, is_sandbox, verified_by_security_layer, ts
)
```

---

## 8. Folder Structure for This Phase

```
agents/
├── django_agent/
│   ├── capability.yaml
│   └── template.md
├── devops_agent/
│   ├── capability.yaml
│   └── template.md
├── docker_agent/
│   ├── capability.yaml
│   └── template.md
└── testing_agent/
    ├── capability.yaml
    ├── template.md
    └── env_verification.py     # confirms execution target resolves to a sandbox, not production
```

---

## 9. Explicitly Out of Scope for This Phase

Code Analysis Engine — still deferred, though this phase surfaces a concrete reason to build it next: it directly constrains Django Agent's usefulness. Deployment execution for DevOps Agent — deferred to its own future phase, mirroring how database write execution got dedicated treatment in Phase 7 rather than riding along with Phase 6. The business agents (Costing, Inventory, Accounting, Manufacturing, Sales, Project Management) — the natural next agent batch, explicitly deferred since this phase is scoped to engineering-platform agents only.

---

## Next

Phase 11: **Code Analysis Engine** — closing the gap this phase surfaced directly (Django Agent's current dependence on documentation-level understanding alone), before the business agents become the next batch.
