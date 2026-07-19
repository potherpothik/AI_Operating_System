# Phase 4 — Context & Prompt Assembly
### Context Builder · Prompt Builder

---

## 0. Priority Decision: Why This Phase Is Fourth

**Why it exists here:** with memory and retrieval built (Phase 3), the system needs the module that decides what actually goes in front of a model and how it's phrased — the last phase before a real agent runs. Context Builder and Prompt Builder are paired because they're sequential halves of one problem: *what the agent sees* (Context Builder) and *how it's structured for this model and this agent role* (Prompt Builder). Neither is meaningfully testable without the other — Prompt Builder needs a real context package to render, Context Builder's output can't be validated without something consuming it.

**Alternatives considered**
- *Skip straight to the first agent (Phase 5) with ad hoc, inline context assembly and prompting* — rejected. This is the most direct route back to "just another chatbot": if context assembly and prompting live inside agent-specific code, every future agent reinvents — and likely under-secures — this logic, and classification-ceiling enforcement (the actual mechanism behind "never send source code externally without approval") has no single place to live.
- *Build Prompt Builder first, treat context as a plain string* — rejected. Prompt-injection defense depends on Prompt Builder knowing which spans came from untrusted retrieved content. Collapsing context into an opaque string before Prompt Builder sees it destroys the distinction the defense needs.
- *Fold this into Phase 5 alongside the first agent* — rejected. Mixes generic, reusable plumbing with one agent's domain-specific behavior, fighting the mandate's own modularity requirement and making both harder to review independently.

**Trade-offs:** four phases in and still nothing agent-visible running end-to-end. Offset by this being deliberately the *last* plumbing phase — everything built here is reusable across all 20+ planned agents, so the investment amortizes instead of being redone per agent.

**Security implications:** Context Builder is the actual enforcement point for *"never send source code to external APIs unless explicitly approved"* — arguably the most safety-critical module built so far, since Security Layer defines policy while this is where that policy meets real content about to reach a model. Prompt Builder's delimiting of untrusted content is the concrete implementation of the injection defense Security Layer only flagged conceptually in Phase 1.

**Performance implications:** token-budget management affects both cost and latency system-wide, since every future agent call passes through it — worth solving the prioritization/truncation strategy once, here, rather than per agent.

**Future scalability:** template-driven Prompt Builder means adding each of the 20+ agents in the mandate is a matter of writing a template, not bespoke prompting code — this is what makes that many agents tractable.

**Estimated complexity:** Medium-high. No new infrastructure dependency (builds entirely on Phases 1 and 3), but real design care in two places: the token-budget/prioritization algorithm, and *structural* — not just conventional — enforcement of untrusted-content delimiting.

---

## 1. Context Builder

**Responsibilities**
- Given a task and the agent capability assigned to it, assembles the minimal-but-sufficient context: relevant memory (short-term/working for this task, relevant business/project memory, relevant decision history) plus relevant Vector Search hits plus any explicit `context_refs` from the task
- Enforces a classification ceiling per call — asks Security Layer what the target model is cleared to see. A local coding model may get the project's normal ceiling; anything that could reach an external API defaults to "public only" unless the Human Approval Layer has explicitly cleared that content for release
- Token/size budget management — decides what to include, exclude, or summarize when retrieved content exceeds the model's context budget, prioritized by recency + relevance score + explicit pins
- Deduplicates overlapping facts surfaced by both memory and vector search
- Tags every included item with provenance (which memory record, which chunk, which decision) so an agent's output can be traced back to what it was actually shown

**Inputs:** `{task, agent_capability, target_model, requested_by}`

**Outputs:** a context package — `{memory_snippets[], retrieved_chunks[], explicit_refs[], classification_ceiling_applied, provenance[], budget_used, budget_total, partial}`

**APIs**

| Endpoint | Purpose |
|---|---|
| `POST /context/build` | Main call: task + agent_capability + target_model → context package |
| `GET /context/{context_id}` | Retrieve a previously built package — explainability and audit |
| `POST /context/pin` | Explicitly pin a fact/doc that must be included regardless of scoring |

**Failure handling:** if Memory Manager or Vector Search is unavailable, degrade *visibly* — mark the package `partial` and note what's missing, rather than silently proceeding as if nothing was lost. Whether to act on partial context is a decision for the agent/Reasoning Engine downstream, not one Context Builder makes silently on its behalf.

**Logging:** every build logged with `context_id`, `task_id`, `classification_ceiling`, and a content hash. The full package is persisted in its own store with its own retention rule rather than duplicated into the audit log itself; the audit log holds the reference.

**Security:** the single enforcement point for the external-API confidentiality rule. Context Builder must know, per build, whether the target model is local-only or external, and apply the matching ceiling accordingly — this is not optional or best-effort.

**Future extension points:** pluggable summarization (a cheap local model compresses low-priority context instead of truncating it); learned relevance scoring, incorporating feedback on whether included context was actually used; multi-turn accumulation for long-running tasks instead of rebuilding from scratch each call.

---

## 2. Prompt Builder

**Responsibilities**
- Renders the actual prompt(s) sent to a model from a context package, the task, and the target agent's template — a rendering engine over templates, not a place for agent-specific logic
- Enforces the structured-output contract the mandate requires of every agent (reasoning, action, confidence, etc. in an agreed schema)
- Injects shared "know when to refuse / know when to delegate / request approval before risky actions" instructions from one fragment library, rather than each agent template redefining this boilerplate
- Structurally delimits untrusted content (retrieved text that might contain embedded adversarial instructions) from system instructions — the mechanical implementation of Security Layer's taint-tracking concept
- Abstracts model-specific formatting (Qwen Coder vs. DeepSeek Coder quirks) so the rest of the system stays model-agnostic

**Inputs:** `{context_package, task, agent_template_id, target_model}`

**Outputs:** rendered prompt (or message list), expected output schema (for validating the model's response), `template_version` used

**APIs**

| Endpoint | Purpose |
|---|---|
| `POST /prompt/render` | context + task + template → rendered prompt + expected schema |
| `GET /prompt/templates` | List available agent templates |
| `POST /prompt/templates` | Register/update a template — approval-gated |
| `POST /prompt/validate-response` | Validate a model's raw response against the expected schema |

**Failure handling:** if a render would exceed the target model's real context limit even after budgeting (e.g. a smaller model swapped in), Prompt Builder refuses to render a silently-truncated prompt — better an explicit budget-exceeded error than a prompt that quietly drops trailing safety instructions.

**Logging:** every render logged with `template_id`, `template_version`, `context_id`, `target_model` — the reproducibility trail for "what exactly was this model told."

**Security:** template changes go through the same approval gate as security-tagged config (Phase 2) — a malicious or buggy template is a real channel for weakening the refuse/delegate/approval instructions baked into every agent. Untrusted-content delimiting is enforced structurally by the render function itself, not left to template authors remembering to add delimiters.

**Future extension points:** template versioning with A/B evaluation against a held-out set before promotion; per-model prompt optimization; native support for tool-calling models alongside plain-text-instruction models behind the same `render()` interface.

---

## 3. How the Two Interact

```
Task Manager hands off a task + assigned agent_capability          [Phase 2]
        │
        ▼
Context Builder.build(task, agent_capability, target_model)
        │
        ├── Memory Manager.query(...)                              [Phase 3]
        ├── Vector Search.query(...)                                [Phase 3]
        ├── Security Layer: classification ceiling for target_model [Phase 1]
        ├── budget / prioritize / dedupe / tag provenance
        └── → context package (persisted, context_id assigned)
                │
                ▼
        Prompt Builder.render(context_package, task, agent_template_id, target_model)
                │
                ├── select template
                ├── slot in context, delimiting untrusted spans
                ├── inject shared refuse/delegate/approval fragment
                └── → rendered prompt + expected output schema
                        │
                        ▼
                (Phase 5: sent to an Ollama-served model)
```

---

## 4. Minimal Data Model for This Phase

```sql
context_package (
  id, task_id, agent_capability, target_model, classification_ceiling,
  budget_used, budget_total, partial, created_at
)
context_item (
  id, context_package_id, source_type, source_id, content_ref,
  provenance, included_reason   -- e.g. 'top-k relevance', 'pinned', 'recency'
)

prompt_template (
  id, agent_template_id, version, body, expected_output_schema,
  requires_approval, approved_by, approved_at
)
prompt_render_log (
  id, context_package_id, template_id, template_version, target_model, rendered_at
)
```

---

## 5. Folder Structure for This Phase

```
assembly/
├── context_builder/
│   ├── api.py
│   ├── retriever.py           # calls Memory Manager + Vector Search
│   ├── budget.py                # token budget + prioritization/truncation
│   ├── classification.py         # ceiling enforcement per target_model
│   └── store.py                  # persisted context packages
└── prompt_builder/
    ├── api.py
    ├── templates/                # one file per agent_template_id
    ├── render.py                  # template + context → prompt, delimits untrusted spans
    ├── shared_fragments.py        # refuse/delegate/approval boilerplate
    └── schema_validate.py         # validates model responses against expected schema
```

---

## 6. Explicitly Out of Scope for This Phase

No actual model calls yet — that's Phase 5. No Planner; "which agent handles this task" is treated as a given input for now, not yet decomposed by an intelligent router. No Documentation Engine / ERP Knowledge Engine content pipelines — still future work feeding Vector Search from Phase 3.

---

## Next

Phase 5: the first real agent, wired end-to-end through Ollama. Given Odoo 19 is the core ERP and this system exists to be its AI brain, **Odoo Agent** is the natural first agent — it proves the full pipeline (Gateway → Task Manager → Context Builder → Prompt Builder → Ollama → response → Audit Logger) in one working path before the remaining agents are built out.
