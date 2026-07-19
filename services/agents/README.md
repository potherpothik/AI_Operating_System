# Phase 5 — Reasoning Engine, Odoo Agent, Database Agent & Planner (working implementation)

Real, tested code. This is the first phase that actually calls a model:
Reasoning Engine is the shared execution loop every agent runs through.
Odoo Agent (Phase 5), Database Agent (Phase 7), and Planner (Phase 8) all
run on it — each a thin capability declaration (`capability.yaml`) plus a
prompt template (`template.md`), not a bespoke service of its own.
Database Agent also needed Reasoning Engine to gain a small,
explicitly-scoped tool-call mechanism (`database_bridge.py`) for its
mandatory dry-run-before-write pattern — the first time this loop calls
back out mid-reasoning rather than just parsing one response and
routing. Planner needed a fail-closed precondition (no model call at all
if Capability Registry is unreachable) and a code-level override on two
of the shared schema's fields (`delegate_to`, `risk_classification`)
whose generic meaning turned out not to apply to a capability whose job
is deciding how work is routed, not doing the work itself.

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
# Optional — closes the Phase 6 loop: an approved odoo.propose_change
# gets materialized as a real branch/commit/push/MR. Without these,
# resume() still completes normally; it just skips execution.
export EXECUTION_URL=http://localhost:8006
export PROPOSAL_REPO_PATH=/tmp/ai_os_sandbox/your-real-repo-clone
# Optional — closes the Phase 7 loop: an approved db.propose_write/
# db.propose_migration actually calls Database Connector. Without this,
# resume() still completes normally; materialize_propose_write just
# reports it wasn't attempted.
export DATABASE_CONNECTOR_URL=http://localhost:8007
# Required for Planner (Phase 8) — without it, any capability="planner"
# execution fails closed before ever calling a model.
export CAPABILITY_REGISTRY_URL=http://localhost:8008
uvicorn main:app --port 8005
```

On startup this service auto-loads every `agents/<name>/capability.yaml`
it finds (currently `odoo_agent`, `database_agent`, and `planner`) into
its own DB, and best-effort attempts to register each agent's prompt
template with Prompt Builder. Template registration is approval-gated
through governance (same as every other template) — a human still has
to approve it once via governance's `/approval` endpoints before any of
them can actually run:

```bash
curl -X POST localhost:8005/odoo_agent/register       # check/retry registration
curl -X POST localhost:8005/database_agent/register
curl -X POST localhost:8005/planner/register
# find the approval_id from the response or GET /approval/pending on governance, then:
curl -X POST localhost:8000/approval/<approval_id>/decide \
  -d '{"decided_by":"human_admin","approve":true}'
curl -X POST localhost:8004/prompt/templates/reconcile-approvals
```

Planner (Phase 8) also needs `GET /capabilities` exposed on this
service (see `main.py` — the source Capability Registry syncs from) and
`CAPABILITY_REGISTRY_URL` pointed at a running Phase 8 service before
it can produce a plan at all; without it, Reasoning Engine fails closed
before ever calling a model, per Phase 8's design.

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
PHASE6_PATH=/path/to/services/execution PHASE7_PATH=/path/to/services/database \
DEMO_ERP_DATABASE_URL=postgresql://user:pass@host:5432/demo_erp \
pytest tests/ -v   # full suite against the live 6-service stack + live Ollama
```

27 tests, all passing against real Postgres (genuine `TIMESTAMPTZ`
columns, confirmed via direct schema inspection, under a deliberately
non-UTC session) and a real live Ollama model — not mocked, except for
deliberately-stubbed tests (see below) used specifically where live-model
phrasing would make a test non-deterministic without changing what's
actually being verified.

## Real bugs found by live testing, not the test suite

- **`qwen3.5:4b` is a thinking-capable model.** Called through Ollama's
  default `/api/generate` behavior, it spent its *entire* output token
  budget on internal chain-of-thought and hit `done_reason: "length"`
  with `response: ""` — never actually writing its answer. This wasn't
  visible from reading the code or from a schema-validity check alone
  (an empty string is just "invalid JSON" either way); it only showed up
  by making a real call and reading the raw API response, including the
  normally-hidden `thinking` field. Fixed by passing `think: false` to
  Ollama — an agent's structured output already carries a `reasoning`
  field, so no separate hidden chain-of-thought is needed — and locked
  in as two permanent regression tests
  (`test_generate_requests_thinking_disabled`,
  `test_live_generate_actually_produces_response_not_empty_string`).
- **The schema-invalid-retry path silently discarded tool-call context**
  (found while building Database Agent's dry-run-before-write flow,
  Phase 7). If a model's response one iteration after a successful
  `db.read`/`db.dry_run` tool call failed schema validation, the retry
  prompt was rebuilt from the *original* task description rather than
  the one carrying the real tool result — silently erasing the data the
  model was supposed to be reasoning from, right when it needed it most.
  Caught by a live model doing exactly this. Fixed in `loop.py` (both the
  schema-retry path and the tool-call-result-injection path now build
  from `current_task_description`, never the original parameter), locked
  in as `test_schema_invalid_retry_does_not_discard_earlier_tool_call_context`.

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
- **Approval → execution is real, not just a status flip** (Phase 6):
  `resume()` on an approved `odoo.propose_change` calls into Phase 6's
  Git Manager via `execution_bridge.py` — confirmed live: a real branch,
  a real commit (with the model's actual proposal text as the file
  content, and the full provenance trailer), and a real push landed in a
  disposable repo, verified by reading that repo's own log and file
  contents directly rather than trusting the returned status.
- **Database Agent's dry-run-before-write pattern is real, live,
  multi-turn agentic behavior** (Phase 7), not a fixed script:
  `database_bridge.py` gives Reasoning Engine a small, explicitly-scoped
  tool-call mechanism — a `db.read`/`db.dry_run` action triggers a real
  call to Database Connector, the actual result gets fed back into the
  model's next turn, and only then can it produce a final
  `db.propose_write` carrying a real impact estimate. The `dry_run_id`
  that eventually authorizes execution is tracked by Reasoning Engine
  itself, never trusted from the model's own response — confirmed live:
  a `db.propose_write` that skips the dry-run step gets approved (risk
  classification alone drives that) but `resume()` refuses to execute it
  since there's no real `dry_run_id` to reference.
- **Planner genuinely routes to a live capability roster, not a
  hardcoded list** (Phase 8): confirmed live — a real `GET /capabilities`
  call happens before any model call, the roster is injected as data
  into context (never baked into the template), and a produced
  `task_graph` creates real Task Manager subtasks with real
  `platform_task_id`s, verified by fetching those tasks back from
  `platform-spine` directly. Two of the shared schema's fields
  (`delegate_to`, `risk_classification`) turned out not to mean the same
  thing for a routing-only capability as they do for an executing one —
  fixed with a structural override in `_decide_routing`, not just a
  prompt instruction, since a live model reasonably applied the generic
  guidance to Planner too.

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
  scope — no live Odoo connection exists.
- **The dry-run/tool-call mechanism is narrowly scoped to `db.read`/
  `db.dry_run`**, not the fully generic tool-calling loop the original
  Phase 5 doc's "tool_call_request... extension point" language gestured
  at — a deliberate, bounded choice for what Database Agent actually
  needed, not the general mechanism a future multi-tool agent would want.

- **A latent Pydantic v2 gotcha in `ExecuteRequest`**: `str = None` on a
  Pydantic model field only sets the default, it doesn't widen the type
  to accept an explicit `null` in a JSON body. Every caller before
  Planner happened to omit optional fields rather than send `null`
  explicitly, so this was live and unnoticed since Phase 5. Fixed with
  `Optional[str] = None`.

## Next

Phase 9: Documentation Engine + ERP Knowledge Engine — every agent built
so far, and Planner itself, has been reasoning over placeholder cached
schema and business memory rather than real ingested documentation.
