# Phase 5 — First Live Agent
### Reasoning Engine · Odoo Agent

---

## 0. Priority Decision: Why This Phase Is Fifth

**Why it exists here:** with Context Builder and Prompt Builder in place (Phase 4), the system can finally assemble what a model should see and how to ask it — this phase closes the loop by actually calling a model and acting on its answer. Reasoning Engine and Odoo Agent are paired for the same reason Context Builder/Prompt Builder were: the generic execution loop can't be meaningfully designed in the abstract, and the first concrete agent can't run without a loop to run it. **Odoo Agent**, specifically — over Django Agent, Database Agent, or any business agent — because Odoo 19 is the actual ERP this system exists to serve. It's the highest-value, most representative first proof, not an arbitrary pick.

**Alternatives considered**
- *Reasoning Engine first, against a placeholder/mock agent* — rejected. Same "the test double becomes the design" risk seen in earlier phases; a fake agent won't exercise real delegation, refusal, or approval paths under real stakes.
- *Start with a lower-risk agent (e.g. a pure documentation-summarizer) to de-risk the loop first* — a legitimate alternative, but rejected here specifically because Odoo Agent's Phase 5 scope is deliberately kept read-only / proposal-only too (no write path exists until Phase 6). It carries comparable risk to a throwaway proof-of-concept while being immediately useful to the actual business.
- *Build all the business agents (Costing, Inventory, Accounting, ...) in one batch once the pattern is proven* — deferred, not rejected. That's the natural Phase 7+, once one agent has validated the pattern.

**Trade-offs:** the first agent gets disproportionate design attention relative to its currently narrow capability — most of this phase's real engineering is Reasoning Engine, which Odoo Agent barely stresses yet (no tool execution, no delegate target that actually exists). Accepted, because the reasoning loop needs to be correct *before* Phase 6 hands any agent something dangerous to execute.

**Security implications:** first phase where a model's output can trigger a real workflow — Human Approval Layer gets its first live request, not a design-time exercise. The model's structured output must itself be treated as untrusted input and re-validated against the agent's declared capabilities before anything downstream trusts it.

**Performance implications:** real inference latency enters the system for the first time. Local model response time (Qwen Coder / DeepSeek Coder, on whatever hardware this runs on) now directly determines end-to-end task latency — loop-iteration bounding matters for both cost and responsiveness.

**Future scalability:** because Odoo Agent is configuration *over* the Reasoning Engine rather than a bespoke implementation, adding Django Agent, Database Agent, and the rest later means writing a capability declaration and a prompt template each — not extending the Reasoning Engine itself. That's the payoff of the Phase 4/5 shared-infrastructure investment.

**Estimated complexity:** Medium. The loop logic and Ollama adapter are genuinely new, but everything they call — Context Builder, Prompt Builder, Security Layer, Human Approval Layer, Audit Logger, Memory/Vector Search — already exists. This phase is mostly wiring plus loop-control, not new foundational architecture.

---

## 1. Reasoning Engine

**Responsibilities**
- The shared execution loop every agent runs through: take a rendered prompt and expected schema from Prompt Builder, call the target model, parse and validate the response, and route based on its declared intent — `final_answer | tool_call_request | delegate_request | refuse | request_approval`
- Ollama adapter: connection management, model routing (which local model for which agent capability), retry/timeout handling, streaming support feeding Gateway's SSE endpoint
- Loop-control: bounds how many reasoning iterations an agent may take per task — a real risk in agentic systems — and records iteration count against the task
- Routes `request_approval` outputs to Human Approval Layer; routes `tool_call_request` to an execution-layer interface that exists only as an extension point in this phase (no real tools until Phase 6); routes `delegate_request` to Task Manager as `needs_agent(X)` when the named agent doesn't exist yet
- Logs every reasoning step, not just the final answer, so the full "model said X, engine decided Y" chain is inspectable

**Inputs:** `{context_id, rendered_prompt, expected_schema, agent_capability, task_id, target_model, max_iterations}`

**Outputs:** `{final_status: completed|refused|awaiting_approval|awaiting_delegation|failed, result, reasoning_trace[], iterations_used}`

**APIs**

| Endpoint | Purpose |
|---|---|
| `POST /reasoning/execute` | Run the loop for a task, return final status |
| `GET /reasoning/{execution_id}/trace` | Full step-by-step reasoning trace |
| `POST /reasoning/{execution_id}/resume` | Resume after an async approval decision returns |

**Failure handling:** model call failures retry with bounded backoff, then surface as `failed` rather than hanging Task Manager indefinitely. Schema-invalid output is never silently accepted — the model is asked to retry once with the validation error appended (bounded), and if it still fails, `failed` status is returned with the raw invalid output attached for debugging. Exceeding `max_iterations` surfaces as `failed: iteration_limit_exceeded`, never a silent truncation.

**Logging:** every iteration — prompt sent, raw response, parsed decision, routing outcome — logged and correlated back to the originating Gateway request via `correlation_id`. This is the operational core of "explainability" as a stated top-level priority.

**Security:** re-verifies the target model matches what Context Builder's classification ceiling was computed for — defense in depth against a bug elsewhere sending over-classified content to the wrong model. Tool-call and delegate requests coming back *from* the model are treated as untrusted (a successful prompt injection upstream could forge them) and re-validated against the agent's actual permitted capability list before being routed anywhere.

**Future extension points:** multi-model ensembling/voting for high-stakes decisions; pluggable loop strategies (simple bounded loop now, richer plan-then-act patterns once Planner exists); streaming intermediate reasoning to the Gateway SSE endpoint for real-time visibility.

---

## 2. Odoo Agent

**Responsibilities**
- Declares a deliberately narrow Phase 5 capability set: read-only Odoo ORM queries (against cached schema/business memory, not a live DB — no Database Connector yet), explaining existing business rules found via Vector Search and business memory, and *drafting* — never committing — proposed changes to Odoo configuration or module code
- Knows when to refuse: direct write requests against production Odoo, or anything outside Odoo's domain (Django engineering-platform questions, DevOps/Docker questions)
- Knows when to delegate: since Django Agent, Database Agent, etc. don't exist yet, "delegation" in this phase means returning a structured `delegate_request` naming which future agent should own the task, rather than attempting it out of scope
- Produces output matching Prompt Builder's schema: reasoning, answer or proposal, confidence, provenance back to the context it was given, and a required `risk_classification` self-assessment — anything above purely informational routes to Human Approval Layer
- Its prompt template states the Phase 5 capability boundary explicitly, so the model is told what it currently can't do rather than left to guess or hallucinate write access

**Capability declaration** (registered with Prompt Builder / Security Layer)
```
capability: odoo_agent
allowed_actions:  [odoo.read_orm, odoo.explain_rule, odoo.propose_change]
forbidden_actions: [odoo.write_orm, odoo.execute_migration, *]   # deny-by-default
requires_approval: [odoo.propose_change]
classification_ceiling: internal
```

**Inputs:** task from Task Manager routed to `agent_capability = "odoo_agent"`

**Outputs:** `{reasoning, answer_or_proposal, confidence, provenance[], risk_classification, delegate_to?}`

**APIs:** none of its own — Odoo Agent is a template plus a capability declaration running on the shared Reasoning Engine, not a separate service. Worth stating explicitly: agents are configuration over shared infrastructure, not independent implementations.

**Failure handling:** if the incoming task falls entirely outside the declared capability set — not even adjacent enough to delegate — Odoo Agent returns a clean, reasoned refusal rather than attempting a best-effort answer outside its scope.

**Logging:** agent-level outcome (accepted / refused / delegated / proposed-pending-approval) logged alongside the generic Reasoning Engine trace, making it possible to later analyze how often Odoo Agent is asked things outside its scope — useful signal for what the next agent should cover.

**Security:** `odoo.propose_change` is the only action in this phase with any real-world effect, and even then only as text for a human to review — no execution capability exists until Phase 6. Deliberately conservative: prove the reasoning/context/prompt pipeline end-to-end before any agent can actually change anything.

**Future extension points:** once Database Connector exists, `odoo.read_orm` can extend to a scoped, audited live query instead of relying on cached schema; once Git Manager exists, `odoo.propose_change` can produce an actual draft commit instead of text a human applies by hand.

---

## 3. How the Two Interact

```
Task (agent_capability = odoo_agent) arrives from Task Manager             [Phase 2]
        │
        ▼
Context Builder.build(...)  →  context package                            [Phase 4]
        │
        ▼
Prompt Builder.render(...)  →  rendered prompt + expected schema           [Phase 4]
        │
        ▼
Reasoning Engine.execute(...)
        │
        ├── Ollama adapter → model (Qwen Coder / DeepSeek Coder)
        ├── parse + validate response against expected schema              [Phase 4]
        ├── decision:
        │     ├── final_answer ─────────────► Task Manager: status=done, result attached
        │     ├── refuse ────────────────────► Task Manager: status=done, reason attached
        │     ├── delegate_request ──────────► Task Manager: status=needs_agent(X)
        │     └── request_approval ──────────► Human Approval Layer.request()          [Phase 1]
        │                                             │  (human decides, async)
        │                                             ▼
        │                                    Reasoning Engine.resume(execution_id)
        │                                             ▼
        │                                    Task Manager: status=done/rejected
        │
        └── every step ──► Audit Logger (full reasoning trace)              [Phase 1]
```

---

## 4. Minimal Data Model for This Phase

```sql
reasoning_execution (
  id, task_id, context_id, agent_capability, target_model,
  status, iterations_used, max_iterations, created_at, completed_at
)
reasoning_step (
  id, execution_id, iteration, prompt_ref, raw_response,
  parsed_decision, routing_outcome, ts
)

agent_capability_def (
  agent_capability, allowed_actions[], forbidden_actions[],
  requires_approval[], classification_ceiling, template_id
)
```

---

## 5. Folder Structure for This Phase

```
agents/
├── reasoning_engine/
│   ├── api.py
│   ├── loop.py                 # bounded execute/resume loop
│   ├── ollama_adapter.py        # model client: routing, retry, streaming
│   └── store.py                  # reasoning_execution / reasoning_step persistence
└── odoo_agent/
    ├── capability.yaml            # allowed/forbidden actions, approval rules, ceiling
    └── template.md                 # registered into Prompt Builder (Phase 4) at startup
```

---

## 6. Explicitly Out of Scope for This Phase

No Git Manager, Shell Executor, or Database Connector — Odoo Agent cannot execute anything yet, only read cached schema/business memory and propose. No Planner — task-to-agent routing is still a given, simplified input. No other agents implemented — Django Agent, Database Agent, etc. exist only as named delegate targets Odoo Agent can point to.

---

## Next

Phase 6: Git Manager + Shell Executor + sandboxing — what turns Odoo Agent's (and every future agent's) proposals into actual, safely executed changes for the first time.
