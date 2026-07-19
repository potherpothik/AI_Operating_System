# Phase 5 — Reasoning Engine & Odoo Agent (working implementation)

Real, tested code. This is the first phase that actually calls a model:
Reasoning Engine is the shared execution loop every future agent runs
through, and Odoo Agent is the first live agent running on it — a thin
capability declaration (`capability.yaml`) plus a prompt template
(`template.md`), not a bespoke service of its own.

## Run it

```bash
pip install -r requirements.txt
# governance, platform-spine, knowledge, and assembly must already be
# running (see the top-level README's four-terminal instructions), and
# Ollama must be running with a model pulled. Then:
export SECURITY_LAYER_URL=http://localhost:8000
export PLATFORM_URL=http://localhost:8002
export KNOWLEDGE_URL=http://localhost:8003
export ASSEMBLY_URL=http://localhost:8004
export OLLAMA_URL=http://localhost:11434   # default, only needed if Ollama runs elsewhere
uvicorn main:app --port 8005
```

On startup this service auto-loads every `agents/<name>/capability.yaml`
it finds (currently just `odoo_agent`) into its own DB, and best-effort
attempts to register Odoo Agent's prompt template with Prompt Builder.
Template registration is approval-gated through governance (same as every
other template) — a human still has to approve it once via governance's
`/approval` endpoints before Odoo Agent can actually run:

```bash
curl -X POST localhost:8005/odoo_agent/register   # check/retry registration
# find the approval_id from the response or GET /approval/pending on governance, then:
curl -X POST localhost:8000/approval/<approval_id>/decide \
  -d '{"decided_by":"human_admin","approve":true}'
curl -X POST localhost:8004/prompt/templates/reconcile-approvals
```

**Model routing note:** the design targets `qwen-coder`/`deepseek-coder`
per the Phase 5 doc, but this environment only has `qwen3.5:4b` pulled.
Rather than edit Phase 2's shipped config defaults, this is handled the
way the config override mechanism was actually built for — a runtime
override, applied once:

```bash
curl -X POST localhost:8002/config/override \
  -d '{"service":"reasoning_engine","key":"default_local_model","value":"qwen3.5:4b","set_by":"human_admin"}'
```

Without this, Context Builder's classification logic (Phase 4) correctly
treats an unrecognized model as untrusted-external and caps retrieval at
`public` — safe, but not what you want if `qwen3.5:4b` genuinely is your
local model.

## Test it

```bash
pytest tests/test_capability_registry.py tests/test_ollama_adapter.py -q   # no live dependencies except the two live-Ollama tests, which skip cleanly if unreachable

SECURITY_LAYER_URL=http://localhost:8000 PLATFORM_URL=http://localhost:8002 \
KNOWLEDGE_URL=http://localhost:8003 ASSEMBLY_URL=http://localhost:8004 \
pytest tests/ -v   # full suite against the live 4-service stack + live Ollama
```

18 tests, all passing against real Postgres (genuine `TIMESTAMPTZ`
columns, confirmed via direct schema inspection, under a deliberately
non-UTC session) and a real live Ollama model — not mocked, except for
one deliberately-stubbed test (see below).

## A real bug found by live testing, not the test suite

`qwen3.5:4b` is a thinking-capable model. Called through Ollama's default
`/api/generate` behavior, it spent its *entire* output token budget on
internal chain-of-thought and hit `done_reason: "length"` with `response:
""` — never actually writing its answer. This wasn't visible from reading
the code or from a schema-validity check alone (an empty string is just
"invalid JSON" either way); it only showed up by making a real call and
reading the raw API response, including the normally-hidden `thinking`
field. Fixed by passing `think: false` to Ollama — Odoo Agent's structured
output already carries a `reasoning` field, so no separate hidden
chain-of-thought is needed — and locked in as two permanent regression
tests (`test_generate_requests_thinking_disabled`,
`test_live_generate_actually_produces_response_not_empty_string`).

## What's real

- **Reasoning Engine**: a real bounded loop — build context (Phase 4) →
  render prompt (Phase 4) → call Ollama → validate the response against
  the template's schema → route. Schema-invalid output gets one retry per
  iteration with the validation error appended to the task description
  (bounded by `max_iterations`, default 8, from Phase 2's Config Manager),
  never silently accepted.
- **The model's output is genuinely treated as untrusted input.** Every
  routing decision re-validates the model's self-declared `action`
  against Odoo Agent's actual `capability.yaml` locally *and* against
  governance's `/security/authorize` — confirmed live: a model response
  that (via a stubbed test) claims `odoo.write_orm` gets refused, not
  trusted, even though nothing in the prompt or template would have
  produced that from a real model (which correctly never claims it).
- **`request_approval` routing is real**: risk-classification above
  `informational` — or an action tagged `requires_approval` in
  `capability.yaml` — creates a genuine pending approval against
  governance, confirmed via a full live round trip: execute → verify
  `awaiting_approval` status via `/reasoning/{id}/trace` → approve via
  governance's real `/approval/{id}/decide` → `/reasoning/{id}/resume` →
  confirmed `completed`.
- **Delegation is real**: when Odoo Agent sets `delegate_to` (confirmed
  live with an out-of-scope Django question), Reasoning Engine creates an
  actual follow-up task in Phase 2's Task Manager and records the real
  `delegate_task_id` — confirmed by fetching that task back from
  platform-spine directly.
- **`agent_capability_def` is genuinely discovered, not hardcoded**: any
  `agents/<name>/capability.yaml` under this package is picked up by
  `capability_registry.load_all()` — adding Django Agent, Database Agent,
  etc. later is a new subfolder, not a code change to Reasoning Engine.

## What's a stub or simplified

- **`needs_agent(X)` delegation reuses Task Manager's existing
  `needs_clarification` status** rather than adding a new state to Phase
  2's state machine, with the target agent name encoded in the task
  description. The Phase 5 doc's own diagram shows a dedicated
  `needs_agent(X)` state; adding that as a real state machine transition
  is a small, well-scoped follow-up once a second agent actually exists
  to consume it — not worth widening Phase 2's surface for a single
  current caller.
- **Odoo Agent's `action` field is an addition on top of the shared
  6-field output schema** (`shared_fragments.py`, Phase 4), not something
  in the original shared contract. It's how Reasoning Engine's routing
  gets a concrete action to check against `capability.yaml` and
  governance's policy — without it, routing could only key off
  `risk_classification`, which is real but coarser. Any future agent that
  doesn't declare per-call actions still works correctly; it just skips
  the capability-based defense-in-depth check and routes on risk alone.
- **`odoo.read_orm` and `odoo.explain_rule` still only see cached
  business memory / vector search**, per the Phase 5 doc's explicit
  scope — no live Odoo connection exists until Phase 7 (Database
  Connector).

## Next

Phase 6: Git Manager + Shell Executor + sandboxing — the execution layer
that turns Odoo Agent's `propose_change` output (currently just approved
text) into something that can actually be applied.
