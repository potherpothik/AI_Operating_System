# Phase 15 — Operations Agents
### Manufacturing Agent · Sales Agent · Project Management Agent

---

## 0. Priority Decision: Why This Phase Now

**Why it exists here:** the natural continuation of Phase 14's business-agent batch (`docs/phases-12-21-remaining-subsystems.md`) — Costing/Accounting/Inventory covered the financial/inventory core; Manufacturing, Sales, and Project Management are the operations side the same doc groups together for a tighter delegate-boundary review (costing feeds sales quoting, inventory feeds manufacturing, both already built).

**Why these three specifically, together:** all three round out the ERP Brain's coverage of day-to-day operations, and their delegate boundaries interlock tightly enough that reviewing them in isolation risks drawing the seams badly — Manufacturing flags material constraints against Inventory's domain, Sales pulls costing output when drafting quotes, and both hand off work to each other and to Costing/Inventory rather than reimplementing any of it.

**Alternatives considered**
- *Build Manufacturing/Sales/PM as three separate phases* — rejected, same reasoning Phase 10 and Phase 14 already established: the marginal cost of the next agent in an already-proven pattern is small, and reviewing the batch's delegate boundaries together is more honest than pretending they're independent.
- *Give Sales Agent blanket access to `res_partner` at whatever classification ceiling it already qualifies for* — rejected outright. This is exactly the mandate's own warning about conflating classification tiers with legal categories: customer PII is a distinct legal category in most jurisdictions, not just "sensitive business data." Collapsing it into the existing `internal`/`confidential` scale would understate what's actually at stake — see Section 3.
- *Have Project Management Agent read Task Manager's database directly* — rejected. Every other agent's real reads go through governed service APIs, never a direct database connection to a peer service's own store; PM Agent gets there the same way, over HTTP, authorized like everything else.

**Trade-offs:** two genuinely new mechanisms this batch needs (PII-scoped column access on Database Connector, Section 3; a `task.read` tool call for Reasoning Engine, Section 4) get less individual scrutiny than a phase built around just one of them would give — accepted because both are small, structurally bounded extensions of patterns already proven (Phase 7's classification scoping; Phase 7/10's tool-call mechanism), not new categories of risk.

**Security implications:** Section 3's PII dimension is this phase's actual security surface — the first time this system distinguishes "sensitive business data" from "identifiable personal data about a real customer," a distinction every other agent's classification-ceiling model doesn't make.

**Performance implications:** none beyond what Phases 5–14 already established.

**Future scalability:** the PII-scoping pattern (a second, orthogonal gate alongside classification_ceiling, keyed by explicit field request + capability authorization) generalizes to any future column carrying identifiable personal data, not just `res_partner.email` — the one PII-shaped column that actually exists in this environment's minimal seeded schema.

**Estimated complexity:** Medium. Two new small mechanisms (PII scoping, `task.read` tool call) plus three capability declarations reusing everything else unchanged.

---

## 1. Manufacturing Agent

```yaml
capability: manufacturing_agent
brain: erp
allowed_actions:
  - manufacturing.explain_workflow
  - manufacturing.propose_schedule_change
  - manufacturing.flag_constraint
forbidden_actions:
  - manufacturing.execute_schedule_direct
requires_approval:
  - manufacturing.propose_schedule_change
classification_ceiling: internal
known_limitation: no live production-scheduling system exists in this environment — propose_schedule_change materializes as a reviewable text document (same path Odoo Agent's own propose_change uses), not a write to a real MRP/scheduling system
```

**Distinctive scope:** draws on ERP Knowledge Engine's ingested workflow knowledge (Phase 9) for `explain_workflow`. `flag_constraint` is a genuine tool call, not a guess — it reuses the exact `db.read` mechanism Database Agent (Phase 7) and Inventory Agent (Phase 14) already established, checking real current stock levels against `demo_erp` before reporting a material constraint, so a flagged shortage reflects an actual queried number, not an inference from retrieved prose alone. `propose_schedule_change` reuses `execution_bridge.materialize_propose_change()` unchanged — a real git-committed proposal document, same as every other agent's text-shaped propose action.

**Refuses:** any direct schedule execution. **Delegates:** material/capacity questions that are really about *what's on hand* → Inventory Agent; the eventual delegate target for Cutlist Optimization Agent (Phase 17) once built — named now even though that agent doesn't exist yet, per the master doc.

---

## 2. Sales Agent

```yaml
capability: sales_agent
brain: erp
allowed_actions:
  - sales.explain_status
  - sales.propose_quote
  - sales.propose_order_change
forbidden_actions:
  - sales.execute_order_direct
  - sales.access_full_customer_pii_unscoped
requires_approval:
  - sales.propose_quote
  - sales.propose_order_change
classification_ceiling: internal
pii_handling: customer PII is a dimension separate from internal/confidential — see Section 3. Sales Agent must explicitly name which PII field(s) a task genuinely needs; anything not named is never returned, regardless of classification_ceiling.
```

**Distinctive scope:** `explain_status` is a genuine tool call over real `sale_order`/`res_partner` data (the same `db.read` mechanism every ERP-reading agent uses), extended with the ability to explicitly request specific PII fields when a task genuinely needs one (e.g., confirming a customer's email before sending a quote) — see Section 3 for the structural gate this goes through, independent of the normal classification-ceiling check every other column already has. `propose_quote` and `propose_order_change` both reuse `execution_bridge.materialize_propose_change()` unchanged.

**Refuses:** direct order execution; unscoped/blanket access to customer PII fields — `sales.access_full_customer_pii_unscoped` is explicitly forbidden, not just undeclared, the same "named deny, not just absent" pattern Inventory Agent's `write_stock_direct` and Accounting Agent's `write_ledger_direct` already established. **Delegates:** cost figures for a quote → Costing Agent (Phase 14) — the `delegate_to` mechanism already handles this structurally; no new code needed for the handoff itself.

---

## 3. The PII Dimension — a Real Extension to Database Connector (Phase 7)

**Why a second, orthogonal gate, not just a stricter classification tier:** `demo_erp.yaml`'s existing column classification (Phase 7) is a single ordered scale — `public < internal < confidential` — and a requester whose ceiling clears `confidential` sees every confidential column, no further questions asked. That model is correct for *business-sensitive* data (a pricing formula, an internal cost basis) but wrong for *identifiable personal data about a real customer*: the mandate's own framing treats these as different legal categories, and a single ordered scale can't express "authorized for confidential business data" without also silently granting "authorized for anyone's email address." Phase 15 is the first agent that would otherwise hit this gap for real.

**The mechanism:**
- A new registry, `services/database/database/database_connector/classification/pii_registry.yaml` — same indirection-registry shape as `secrets_registry.yaml` (Phase 7) and `environment_registry.yaml` (Phase 10): which columns are PII-tagged per target, and which capabilities are authorized to request PII fields *at all* for that target.
- `QueryRequest` gains one new field: `pii_fields_requested: list[str]` — a task-scoped, explicit declaration of exactly which PII-tagged column(s) this specific query genuinely needs. Never inferred, never defaulted to "all."
- `/db/query`'s existing classification-ceiling filtering (`filter_columns`) now **skips PII-tagged columns entirely** rather than deciding them — genuinely orthogonal means a PII column isn't a point on the public/internal/confidential scale at all, not even at the top of it. A **second**, independent filter (`filter_pii_columns`) is the sole decision-maker for PII-tagged columns: included only if (a) the requesting capability is on that target's `authorized_capabilities` list, checked up front as a 403 gate, **and** (b) the column name appears in `pii_fields_requested` for this specific query. Found live: an earlier version layered the PII check *on top of* the ceiling check, which meant Sales Agent — deliberately kept at `classification_ceiling: internal`, never `confidential`, since it has no business seeing confidential data in general — could never see `email` even with an authorized, explicit request, because the ceiling gate silently vetoed it first. Two genuinely separate gates fixes this: a capability's ceiling governs ordinary business-sensitivity columns, and the PII registry alone governs PII columns, independent of what that capability's ceiling happens to be.
- A request that includes any `pii_fields_requested` names calls `Security Layer.authorize()` for a new `db.read_pii` action before the query even runs — the same authorize-then-log discipline every other governed read already follows, giving PII access its own distinct audit trail (`decision`, `capability`, exactly which fields) separate from the routine `db.read` log line.

**Failure handling:** requesting a PII field the capability isn't authorized for is a 403, not a silent redaction — the caller (a model, ultimately) needs to know its request was refused, the same "don't silently under-serve without saying so" discipline Context Builder's own classification-ceiling logging already follows.

**Explicitly not attempted:** a general PII taxonomy across every table/service in this system — this phase scopes the mechanism to exactly the one PII-shaped column that exists in this environment's minimal seeded schema (`res_partner.email`), structurally ready to extend to more columns via the same registry the moment a real schema has more of them.

---

## 4. Project Management Agent

```yaml
capability: project_management_agent
brain: erp
allowed_actions:
  - pm.explain_status
  - pm.propose_milestone_update
  - pm.flag_at_risk
forbidden_actions:
  - pm.close_project_direct
requires_approval:
  - pm.propose_milestone_update
classification_ceiling: internal
known_limitation: no live Odoo project-management module exists in this environment — "customer-facing ERP project" status draws on ERP Knowledge Engine's ingested workflow content (Phase 9) rather than a live query, since demo_erp's minimal seeded schema has no project table; "orchestration layer's own task history" IS a real, live query (Section 4's task.read tool call)
```

**Distinctive scope:** the first agent reasoning over two genuinely different kinds of "project" — a customer-facing ERP project (documentation-level understanding only, per the known limitation above) *and* the orchestration layer's own task history (Task Manager's `Task`/`TaskEvent` records, Phase 2) — meaning it can explain both "why is this customer project behind schedule" and "why did this AI task take so long," a slightly meta capability none of the other agents have. The task-history half is a genuine tool call, not retrieved prose: a new `task.read` action (mirroring `db.read`'s two-step shape) that Reasoning Engine resolves against a real call to Task Manager's Gateway, feeding the actual task state and its real event history back into context before PM Agent produces a final answer.

**The one real gap this surfaced in Phase 2:** `store.task_events()` already existed in `platform_spine/task_manager/store.py` — nothing in Phase 2 had ever needed the full transition history over HTTP before, only the current task snapshot (`GET /api/v1/tasks/{id}`). A new `GET /api/v1/tasks/{task_id}/events` endpoint closes that gap — the same "extend by unblocking an existing gap" pattern this project's whole history follows, not new surface invented for its own sake.

**Refuses:** closing a project directly. **Delegates:** nothing named explicitly in the master doc; in practice, cost or schedule detail behind a milestone risk → Costing Agent / Manufacturing Agent as appropriate.

---

## 5. How the New Mechanisms Fit In

```
Sales Agent → sales.explain_status(needs customer email for a quote)
        │
        ▼
db.read tool call, pii_fields_requested=["email"]
        │
        ▼
Database Connector: classification-ceiling filter (unchanged)
        │                    then
        ▼
PII filter: sales_agent on demo_erp's authorized_capabilities? "email" in pii_fields_requested?
        │                                        │
       yes                                       no
        ▼                                        ▼
Security Layer.authorize("db.read_pii")   column excluded, same as any
        │                                  other denied column
        ▼
real email value returned, logged distinctly from the base db.read decision


Project Management Agent → pm.explain_status("why is this AI task slow?")
        │
        ▼
task.read tool call (task_bridge.py)
        │
        ▼
GET /api/v1/tasks/{id} + GET /api/v1/tasks/{id}/events  (new endpoint, Phase 2 gap-fill)
        │
        ▼
real task status + real transition history fed back into context
        │
        ▼
pm.explain_status final answer, grounded in real data
```

---

## 6. Minimal Data Model

```sql
-- Database Connector (Phase 7) — no new table, a new registry file only:
-- services/database/database/database_connector/classification/pii_registry.yaml
--   target_db -> { pii_columns: {table: [columns]}, authorized_capabilities: [...] }

-- No new table anywhere else this phase touches — every new mechanism
-- reads existing tables (Task, TaskEvent, ApprovalRequest-shaped audit
-- trail via governance's own log_event, DbQueryLog for the db.read_pii
-- audit trail).
```

---

## 7. Folder Structure

```
services/agents/agents/
├── manufacturing_agent/
│   ├── capability.yaml
│   └── template.md
├── sales_agent/
│   ├── capability.yaml
│   └── template.md
└── project_management_agent/
    ├── capability.yaml
    └── template.md

services/agents/agents/reasoning_engine/
└── task_bridge.py          # new — task.read tool call

services/database/database/database_connector/
└── classification/
    └── pii_registry.yaml   # new — PII column + authorized-capability registry
```

---

## 8. Explicitly Out of Scope

A general PII taxonomy across every table this system might ever touch — scoped to `res_partner.email`, the one column that exists, structurally ready to extend. Real production scheduling / MRP integration for Manufacturing Agent. Real order execution for Sales Agent. A genuine multi-project Gantt/dependency model for Project Management Agent beyond status/milestone/at-risk flagging. Cutlist Optimization Agent (Phase 17) — named as Manufacturing Agent's future delegate target, not built here.

---

## Next

Phase 16–18: code-quality, engineering, and cross-cutting agents (Code Review Agent, Reverse Engineering Agent, Architecture Agent, Calculation Agent, Cutlist Optimization Agent, Python Agent, Documentation Agent, Security Agent, Research Agent) — the Coding Brain's remaining coverage, and the natural first consumers of Phase 11's Code Analysis Engine. Phase 22 (Coding Agent Gateway) remains available as an alternative next step if the Coding Brain becomes the priority instead.
