# Phase 18 — Cross-Cutting Agents
### Python Agent · Documentation Agent · Security Agent · Research Agent

---

## Prerequisites (read before implementation)

| Doc | Why |
|---|---|
| [`docs/README.md`](README.md) | Doc index and before-you-code checklist |
| [`phase-1-governance-layer.md`](phase-1-governance-layer.md) | Audit Logger — Security Agent's real `security.audit_query` reads this directly |
| [`phase-9-documentation-erp-knowledge-engine.md`](phase-9-documentation-erp-knowledge-engine.md) | Documentation Engine — Documentation Agent's real content source and, once approved, real write target |
| [`phase-16-code-quality-agents.md`](phase-16-code-quality-agents.md) | Reverse Engineering Agent — Documentation Agent's own delegate target when nothing is written down; `reverse_eng_bridge.py`'s chained docs-ingest is reused unchanged for a second agent |

---

## 0. Priority Decision: Why This Phase Now

**Why it exists here:** the master roadmap's own grouping — four agents that don't share a domain the way the ERP batch (Phase 14/15) or the engineering batch (Phase 17) did, but do share a posture: each one is explicitly told what it is *not* allowed to become. Python Agent must actively check for and defer to Odoo/Django-specific agents rather than defaulting to answering. Documentation Agent works from what's already written, deferring to Reverse Engineering Agent (Phase 16) the moment nothing is. Security Agent's name doesn't grant it Security Layer's actual enforcement authority — it's advisory, the same relationship Code Review Agent (Phase 16) has to an actual merge. Research Agent's default posture is internal-only, actively resisting the pull its own name suggests toward reaching outward.

**Why these four together:** CLAUDE.md's own framing already anticipated this — "most Phase 18 work is config, not a new FastAPI service." Three of the four genuinely need zero new mechanism, reusing `execution_bridge.materialize_propose_change()` (every `propose_*` action) and, for Documentation Agent specifically, Phase 16's `reverse_eng_bridge.py` chained docs-ingest step unchanged for a second agent. The one genuine exception — Security Agent's real audit query — is a small, real tool call against Phase 1's existing Audit Logger, plus one honest, small gap-fill on it.

**Alternatives considered**
- *Let Security Agent's `security.audit_query` return whatever prose the model recalls from retrieved context* — rejected. An audit trail is exactly the kind of thing that must be real or explicitly absent, never approximated; this reuses the same "real tool call, real data fed back" discipline every prior phase's read actions already established (`db.read`, `task.read`, `review.fetch_diff`).
- *Build a genuine external-web-access tool for Research Agent's `propose_external_lookup`* — rejected outright. This system has no external web-access tool anywhere in its history, by explicit offline-first design (`docs/architecture-vision.md`). An "approved" external lookup materializes as a real, reviewable proposal document (what to look up, why) for a human to act on manually — never an automated fetch this system doesn't have the means, or the mandate, to perform itself.
- *Give Documentation Agent its own bespoke docs-ingest bridge* — rejected. Phase 16's `reverse_eng_bridge.materialize_propose_documentation()` is already fully generic (it only reads `execution.task_id`/`execution.agent_capability`/the git-committed file path) — reusing it for a second agent's `docs.propose_new_doc` costs zero new code and proves the bridge was built generically the first time, not accidentally agent-specific.
- *Implement real classification-scoped audit visibility for Security Agent* — rejected for this phase. `AuditEvent` (Phase 1) has no classification field at all today; building real per-event scoping is a materially larger change to the audit log's own schema than this phase's real scope, and is named honestly as a gap rather than silently faked with cosmetic filtering.

**Trade-offs:** Security Agent's `security.audit_query` returns exactly what governance's existing, unauthenticated `GET /audit/query` already returns to anyone — no new visibility restriction, and the "audit access is itself classification-scoped" framing in the master doc is only partially realized (governed by whether `security_agent`'s own role is granted the read at all, not by per-event content scoping).

**Security implications:** Security Agent recommending something is explicitly never Security Layer authorizing it — its own `capability.yaml` has zero `require_approval` actions, matching Code Review Agent's precedent that advisory output isn't itself a governed decision.

**Performance implications:** none beyond what Phases 5–17 already established.

**Future scalability:** Documentation Agent's reuse of `reverse_eng_bridge.py` is the first confirmation that Phase 16's chained-materialization pattern generalizes cleanly to a second agent — any future agent whose approved proposal should become real Documentation Engine content can reuse the same bridge unchanged.

**Estimated complexity:** Low-medium. One real gap-fill (`correlation_id` filter on `GET /audit/query`), one new bridge (`security_bridge.py`), everything else is pure reuse.

---

## 1. Python Agent

```yaml
capability: python_agent
brain: coding
allowed_actions:
  - python.explain_code
  - python.propose_script
  - python.propose_change
forbidden_actions:
  - python.execute_direct
requires_approval:
  - python.propose_change
classification_ceiling: internal
routing_note: checks first whether a request is actually Odoo- or Django-specific and delegates rather than attempting generically
```

**Distinctive scope:** needs no new mechanism at all. `python.explain_code` reasons from Code Analysis Engine's structural prose (Phase 11), already retrieved into context like every other `explain_*` action. `python.propose_script` and `python.propose_change` both reuse `execution_bridge.materialize_propose_change()` unchanged. The real discipline this agent needs is entirely a prompt-level one: since "Python" genuinely spans Odoo Agent's and Django Agent's own lanes, its template is built to actively check for and hand off an Odoo- or Django-specific request via the existing `delegate_to` mechanism (Phase 4/5) rather than attempting a generic Python answer to a question that's really about one of those platforms specifically.

**Refuses:** `python.execute_direct` — even a Python agent never runs code outside Shell Executor's own normal gated path (Phase 6); there is no direct-execution action in its capability at all, not even a forbidden-but-namable one beyond the wildcard.

---

## 2. Documentation Agent

```yaml
capability: documentation_agent
brain: coding
allowed_actions:
  - docs.answer_from_existing
  - docs.propose_new_doc
forbidden_actions:
  - docs.publish_direct
requires_approval:
  - docs.propose_new_doc
classification_ceiling: internal
boundary_note: works from existing written sources; Reverse Engineering Agent (Phase 16) is the delegate target when nothing is written down at all
```

**Distinctive scope:** `docs.answer_from_existing` reasons strictly from Documentation Engine's real ingested content (Phase 9) — if the retrieved context doesn't cover the question, the correct move is `delegate_to "reverse_engineering_agent"`, never inventing an answer from inference (that is explicitly Reverse Engineering Agent's own, differently-labeled lane). `docs.propose_new_doc` reuses `execution_bridge.materialize_propose_change()` for its git-commit half, then — the one small, real extension this agent needed — chains into Phase 16's `reverse_eng_bridge.materialize_propose_documentation()` completely unchanged, added to `loop.py`'s `REVERSE_ENG_PROPOSE_ACTIONS` set for a second capability. An approved new doc becomes real, independently-queryable Documentation Engine content the same way a confirmed reverse-engineering draft already does.

**Refuses:** `docs.publish_direct` — a proposed doc is never treated as published until the same human-approval-then-git-then-ingest path every other proposal goes through completes for real.

---

## 3. Security Agent

```yaml
capability: security_agent
brain: coding
allowed_actions:
  - security.review_change
  - security.explain_risk
  - security.audit_query
forbidden_actions:
  - security.modify_policy_direct
  - security.grant_permission
requires_approval: []
classification_ceiling: internal
note: purely advisory; has no special authority over Security Layer's actual enforcement despite the shared name. Audit access is intended to be classification-scoped per the master roadmap; AuditEvent (Phase 1) has no classification field today, so this phase's real audit_query returns the same unscoped record set governance's existing GET /audit/query already returns to any caller — named explicitly as a real, unresolved gap, not silently narrowed.
```

**Distinctive scope:** `security.review_change` and `security.explain_risk` are informational, reasoning from retrieved policy/context. `security.audit_query` is a real, non-terminal tool call — the one genuinely new bridge this phase needed (`security_bridge.py`, mirroring `database_bridge.py`'s shape) calls governance's real `GET /audit/query` and feeds the actual matching events back into context, never a model's guess about what "probably" happened. This surfaced one small, real gap: `GET /audit/query` (Phase 1) only ever supported `actor_id`/`action` filters — no `correlation_id`, the standard way this system threads a single task's related events together (already used by `audit_log()` callers everywhere, and the exact filter Phase 24's own planned audit-timeline view assumes exists). Closed by adding `correlation_id` as a third optional filter, extending the existing query rather than adding a new endpoint.

**Refuses:** `security.modify_policy_direct`, `security.grant_permission` — this agent recommending something is never Security Layer actually deciding it. No action in this capability ever requires its own human approval — same posture as Code Review Agent (Phase 16): the output is advisory, not a decision that itself needs gating.

---

## 4. Research Agent

```yaml
capability: research_agent
brain: coding
allowed_actions:
  - research.synthesize_internal
  - research.propose_external_lookup
forbidden_actions:
  - research.access_external_direct
requires_approval:
  - research.propose_external_lookup
classification_ceiling: internal
note: default posture is internal-knowledge-only; external access requires the same explicit approval any external-model release does. This system has no external web-access tool anywhere in its history (offline-first by design, docs/architecture-vision.md) — an approved external-lookup proposal is a real, reviewable document describing what to look up and why, for a human to act on manually. It is never an automated fetch, since no such mechanism exists in this codebase.
```

**Distinctive scope:** `research.synthesize_internal` reasons from Vector Search / Documentation Engine / ERP Knowledge Engine content already retrieved into context — internal knowledge only, the explicit default posture. `research.propose_external_lookup` reuses `execution_bridge.materialize_propose_change()` unchanged, same as every other `propose_*` action — its approval requirement is unconditional (`requires_approval` always fires, no risk-based exception), matching the master doc's own framing that external access is opt-in, never default.

**Refuses:** `research.access_external_direct` — there is no code path anywhere in this agent, or in the bridge it uses, that reaches an actual external network call. The forbidden action names a capability this system has simply never built, not a gate holding back one that exists.

---

## 5. How the Reused Mechanisms Fit In

```
Documentation Agent → docs.propose_new_doc
        │
        ▼
human approves (existing approval flow, unchanged)
        │
        ▼
resume() → execution_bridge.materialize_propose_change() (existing,
           unchanged) → real branch/commit/push of proposals/{task_id}.md
        │
        ▼
reverse_eng_bridge.materialize_propose_documentation() (Phase 16,
REUSED UNCHANGED for a second agent) → real POST /docs/ingest
        │
        ▼
real, independently-queryable documentation


Security Agent → security.audit_query(correlation_id="task-xyz")
        │
        ▼
security_bridge.py (NEW) → real GET /audit/query?correlation_id=task-xyz
        │                   (Phase 1, extended with this one new filter)
        ▼
real matching audit events fed back into context
        │
        ▼
security.explain_risk / security.review_change — grounded in the real trail
```

---

## 6. Minimal Data Model

No new tables this phase — `security.audit_query` reads existing `AuditEvent` rows (Phase 1); every proposal materializes into existing `Task`/`ApprovalRequest`/git/Documentation Engine records already established by Phases 1/6/9/16.

---

## 7. Folder Structure

```
services/agents/agents/
├── python_agent/
│   ├── capability.yaml
│   └── template.md
├── documentation_agent/
│   ├── capability.yaml
│   └── template.md
├── security_agent/
│   ├── capability.yaml
│   └── template.md
└── research_agent/
    ├── capability.yaml
    └── template.md

services/agents/agents/reasoning_engine/
└── security_bridge.py     # new — security.audit_query tool call

services/governance/governance/audit/
└── api.py                 # extended — correlation_id filter on GET /audit/query
```

---

## 8. Explicitly Out of Scope

Real classification-scoped audit visibility (Section 0's trade-off). An actual external web-access tool for Research Agent — this system remains offline-first; `propose_external_lookup` only ever produces a document for a human, never a fetch. Python Agent executing anything itself, direct or otherwise — every code-touching action of its own is `propose_*`, gated the same as any other agent's.

---

## Next

Phase 19–21: Deployment Architecture, Backup Strategy/Disaster Recovery, and a consolidated reference doc — infrastructure and operational concerns rather than new agent capabilities, the natural next section of the consolidated roadmap now that every agent batch through Phase 18 is built. Phase 22 (Coding Agent Gateway) and Phase 24 (Control UI) remain available to prioritize instead once external-tool or operator-UI work is ready to start.
