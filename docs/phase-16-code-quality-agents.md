# Phase 16 — Code-Quality Agents
### Code Review Agent · Reverse Engineering Agent · Architecture Agent

---

## 0. Priority Decision: Why This Phase Now

**Why it exists here:** the master roadmap's own framing — "the natural first consumers of Code Analysis Engine (Phase 11)" — a real capability (structural code knowledge: signatures, docstrings, call graph) has existed since Phase 11 with no agent actually reasoning over it yet. Phase 15 closed out the ERP Brain's operations batch; this phase is the Coding Brain's first genuine batch (all three agents are `brain: coding`), a deliberate pivot after five straight ERP-side phases (12/14/15's business agents).

**Why these three together:** they interlock the same way Phase 15's batch did — Architecture Agent is the delegate target Django Agent and Database Agent's prompts *already* name (`services/agents/agents/database_agent/template.md`: "delegate_to 'architecture_agent' if you recognize one"), so building it closes an existing dangling reference rather than adding a new one. Code Review Agent and Reverse Engineering Agent both consume Code Analysis Engine's call graph and structural prose respectively, from opposite ends: one reviews *new* proposed changes before a human approves them, the other reconstructs understanding of *existing* undocumented code after the fact.

**Alternatives considered**
- *Auto-trigger Code Review Agent from every other agent's `resume()` flow, so every proposed change gets reviewed automatically before a human ever sees it* — rejected as materially larger than this phase's real scope. It would mean touching every existing agent's materialization path (Phase 5 through 15) to insert a synchronous review step, a change with its own separate blast radius worth its own review. This phase builds Code Review Agent as a standalone capability a human (or a future orchestration layer) can invoke against a specific branch, with its assessment attachable to an existing pending approval — real, usable, and honest about not being wired into every other agent's flow yet.
- *Skip the Human Approval Layer extension and have Code Review Agent's assessment live only in its own `ReasoningExecution.result`* — rejected. The doc's own framing is explicit: "an additional input to the Human Approval Layer request, not a replacement for the human's judgment." A review a human approver has to separately go looking for in a different service defeats that framing; it needs to show up ON the approval record itself.
- *Have Reverse Engineering Agent write directly into Vector Search, bypassing Documentation Engine* — rejected. Every other piece of durable knowledge in this system enters through the service that owns classification/provenance for its type (Costing Agent's formulas go through ERP Knowledge Engine's registration, not a raw Vector Search write). Documentation Engine already has a real, working `/docs/ingest` path; reusing it costs nothing and keeps this content's provenance consistent with every human-authored doc.

**Trade-offs:** the new Human Approval Layer extension (Section 3) is this phase's actual security surface — the first time a SECOND agent's structured output attaches to another agent's pending human-facing decision, not just its own. Scoped narrowly (append-only, advisory, never changes an approval's own decision) to keep that surface small.

**Security implications:** an attached review is read-only additive context for the human approver — it cannot approve, reject, or auto-decide anything itself (`review.approve_recommendation` is exactly that: a *recommendation*, not a decision). Documented explicitly in Section 3's failure handling.

**Performance implications:** none beyond what Phases 5–15 already established.

**Future scalability:** the attach-review mechanism generalizes to any future advisory agent (a Security Agent, a Cost-Impact Agent) wanting to add structured input to a pending approval without needing its own bespoke channel.

**Estimated complexity:** Medium-high. One genuinely new governance mechanism, one new tool-call bridge (`review_bridge.py`), one chained-materialization bridge (`reverse_eng_bridge.py`), three capability declarations — the third (Architecture Agent) needs no new mechanism at all.

---

## 1. Code Review Agent

```yaml
capability: code_review_agent
brain: coding
allowed_actions:
  - review.fetch_diff
  - review.check_callers
  - review.flag_concern
  - review.approve_recommendation
forbidden_actions:
  - review.merge
  - review.override_human_approval
classification_ceiling: internal
requires_approval: none — its own output is advisory, feeding INTO approval rather than bypassing it
known_limitation: not automatically triggered by any other agent's propose_* flow this phase — invoked directly (by a human or a future orchestration layer) against a specific branch, per this phase's own scope decision (Section 0)
```

**Distinctive scope:** two real, non-terminal tool calls, mirroring `database_bridge.py`'s exact shape — `review.fetch_diff` calls Git Manager's existing `POST /git/diff` (Phase 6) against a real branch in `PROPOSAL_REPO_PATH`, and `review.check_callers` calls Code Analysis Engine's existing, unauthenticated `GET /graph` (Phase 11) for a specific symbol's real callers — "checking whether a change breaks a caller elsewhere" becomes a real graph lookup, not an inference from the diff text alone. **Found live, not by inspection:** the first version called `GET /symbol/{ref}` instead, whose own `callers`/`callees` lists are raw internal symbol ids, not human-readable qualified names — useless for a model (or a human reading its final assessment) to reason about; `GET /graph` already resolves every edge to real qualified names, so the fix was picking the right one of two existing endpoints, not adding new code to either service. A second live bug in the same feature: a bare branch name passed straight to `git diff` compares that branch's tip to the current working tree, not to `main` — empty right after a clean checkout. Fixed by building `main...{branch}` automatically in `review_bridge.py` rather than pushing git range syntax onto the model. Both of Code Review Agent's terminal actions (`review.flag_concern`, `review.approve_recommendation`) never require human approval themselves — but when the model's response names a real `target_approval_id` (an existing pending approval it's reviewing), Reasoning Engine synchronously attaches the review to that approval via the new mechanism in Section 3, right when `execute()` finalizes (no `resume()` step needed, since there's no approval gate on Code Review Agent's own output).

**Refuses:** merging anything, overriding a human's decision. **Delegates:** nothing named explicitly — a review that's really about "should we grant this permission" belongs to a human, not a delegate.

---

## 2. Reverse Engineering Agent

```yaml
capability: reverse_engineering_agent
brain: coding
allowed_actions:
  - reverse_eng.explain_undocumented
  - reverse_eng.propose_documentation_draft
forbidden_actions:
  - reverse_eng.modify_code_direct
requires_approval:
  - reverse_eng.propose_documentation_draft
classification_ceiling: internal
note: output is explicitly labeled inferred/reconstructed, never presented with the confidence of documented fact — enforced by the agent's own prompt template, not a structural gate
```

**Distinctive scope:** `explain_undocumented` reasons from Code Analysis Engine's structural prose (signatures, docstrings, call graph — already in Vector Search since Phase 11) already present in retrieved context, no new tool call needed. `propose_documentation_draft` reuses `execution_bridge.materialize_propose_change()` completely unchanged for the git-commit half (same `proposals/{task_id}.md` document every other agent's propose action produces) — but Reverse Engineering Agent is the first agent whose approved proposal does something *after* that: the one genuinely new bridge this phase needs (`reverse_eng_bridge.py`) calls Documentation Engine's already-existing `POST /docs/ingest` (Phase 9) pointing at that SAME just-committed file, closing the loop from inference to record the doc's own framing describes. A confirmed-accurate draft becomes real, independently-queryable documentation — not a second copy sitting in a different agent's own output table.

**Refuses:** modifying code directly. **Delegates:** nothing named explicitly.

---

## 3. The Approval-Review Attachment Mechanism — a Real Extension to Governance (Phase 1)

**Why a new mechanism, not a workaround:** Phase 1's `ApprovalRequest` carries exactly one `payload_ref` string, written once at creation by whichever agent's own proposal is pending — there was never a second agent's structured input to attach to it, because no second agent existed. Code Review Agent is the first.

**The mechanism:**
- A new table, `ApprovalReview` (`services/governance/governance/models.py`): `id`, `approval_id` (FK-shaped, not a real constraint — same posture as every other cross-table reference in this codebase), `reviewer_capability`, `verdict` (`concern` | `recommend_approve`), `reasoning`, `created_at`. Append-only — a review is never edited or deleted, only added.
- `POST /approval/{approval_id}/attach_review` — takes `reviewer_capability`, `verdict`, `reasoning`. Fails with a clean 404 if the target approval doesn't exist; succeeds regardless of the approval's current status (a review can legitimately arrive after a decision was already made, as a record of what was said, though a human approver obviously only benefits from seeing it before deciding).
- `GET /approval/{approval_id}` (existing endpoint) gains a `reviews: [...]` array in its response — every attached review, oldest first. No change to `GET /pending` or `GET /approval` (the listing endpoints) — reviews are a detail-view concern, matching how `payload_ref` itself already isn't surfaced on the listing endpoints either.

**Failure handling:** an attach-review call for a nonexistent `approval_id` is a clean 404, never silently dropped. `attach_review` itself performs no authorization decision of its own beyond the standard `authorize()`/audit-log discipline every write in this system already follows — it cannot change `status`, `decided_by`, or anything else on the approval record itself; the human's decision path is completely unaffected by whether a review exists.

**Explicitly not attempted:** automatic triggering (Section 0); a structured schema for `reasoning` beyond free text — matching how `payload_ref` itself is free text today, a deliberate parity choice rather than over-building the new field beyond what the old one already does.

---

## 4. Architecture Agent

```yaml
capability: architecture_agent
brain: coding
allowed_actions:
  - architecture.explain_existing
  - architecture.propose_decision
forbidden_actions:
  - architecture.implement_direct
requires_approval:
  - architecture.propose_decision
classification_ceiling: internal
output_requirement: every proposal must address why / alternatives / trade-offs / security / performance / scalability / complexity — enforced by the agent's own prompt template, the same seven-question standard this project's own design docs (including this one) are held to
```

**Distinctive scope:** needs no new mechanism at all — `explain_existing` reasons from retrieved context (ERP Knowledge Engine's schema prose, Code Analysis Engine's structural prose), and `propose_decision` reuses `execution_bridge.materialize_propose_change()` completely unchanged. The only real "wiring" this phase needed for Architecture Agent already existed: Database Agent's own prompt template has said `delegate_to "architecture_agent" if you recognize one` since Phase 7, written when Architecture Agent didn't exist yet — building it now makes that delegation actually resolve to something real for the first time, with zero changes to Database Agent's own template.

**Refuses:** implementing a decision directly — it proposes, a human and the actual implementing agent do the rest.

---

## 5. How the New Mechanisms Fit In

```
Code Review Agent ← asked to review a real branch, with an existing
                     approval_id it should attach findings to
        │
        ▼
review.fetch_diff → real POST /git/diff (Phase 6, existing;
                     compared against main automatically)
        │
        ▼
model reads real diff, optionally names a specific symbol
        │
        ▼
review.check_callers → real GET /graph (Phase 11, existing,
                        unauthenticated structural tier — resolves
                        edges to real qualified names, unlike
                        GET /symbol/{ref}'s own raw-id caller list)
        │
        ▼
review.flag_concern / review.approve_recommendation (terminal, no
approval gate on Code Review Agent's OWN output)
        │
        ▼
execute() finalizes → synchronously calls
POST /approval/{target_approval_id}/attach_review (NEW, Section 3)
        │
        ▼
a human approver's GET /approval/{id} now shows the real review
alongside the original proposal — informs, never decides


Reverse Engineering Agent → reverse_eng.propose_documentation_draft
        │
        ▼
human approves (existing approval flow, unchanged)
        │
        ▼
resume() → execution_bridge.materialize_propose_change() (existing,
           unchanged) → real branch/commit/push of proposals/{task_id}.md
        │
        ▼
reverse_eng_bridge.materialize_propose_documentation() (NEW, thin) →
real POST /docs/ingest (Phase 9, existing) pointed at that same file
        │
        ▼
real, independently-queryable documentation — not a second copy
```

---

## 6. Minimal Data Model

```sql
-- services/governance — new table
CREATE TABLE approval_review (
    id TEXT PRIMARY KEY,
    approval_id TEXT NOT NULL,
    reviewer_capability TEXT NOT NULL,
    verdict TEXT NOT NULL,          -- concern | recommend_approve
    reasoning TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

-- No other new tables this phase — every other mechanism reads/writes
-- existing tables (ReasoningExecution, ApprovalRequest itself, DocSource/
-- doc_ingestion_log via the existing /docs/ingest path).
```

---

## 7. Folder Structure

```
services/agents/agents/
├── code_review_agent/
│   ├── capability.yaml
│   └── template.md
├── reverse_engineering_agent/
│   ├── capability.yaml
│   └── template.md
└── architecture_agent/
    ├── capability.yaml
    └── template.md

services/agents/agents/reasoning_engine/
├── review_bridge.py           # new — review.fetch_diff / review.check_callers tool calls, attach_review materialization
└── reverse_eng_bridge.py      # new — chained docs-ingest after git materialization

services/governance/governance/approval/
└── api.py                     # extended — POST /{id}/attach_review, reviews[] on GET /{id}
```

---

## 8. Explicitly Out of Scope

Automatic triggering of Code Review Agent from another agent's own propose/resume flow (Section 0). A structured (non-free-text) review schema. Any change to how a human's own approve/reject decision is made or weighted — an attached review is context, never a vote. Security Agent, Research Agent (named in the master roadmap's Phase 18 block) — cross-cutting agents that could plausibly also want to attach structured input to an approval, deferred to whichever phase actually builds them, reusing this same mechanism unchanged.

---

## Next

Phase 17: Engineering & Calculation Agents (Calculation Agent, Cutlist Optimization Agent — Manufacturing Agent's already-named future delegate target from Phase 15). Phase 18: Cross-Cutting Agents (Security Agent, Research Agent) — natural next consumers of this phase's approval-review attachment mechanism.
