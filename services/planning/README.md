# Phase 8/30 — Planner & Capability Registry + Declarative Workflows (working implementation)

Real, tested code. The first phase where `agent_capability` stops being a
given input — Planner decomposes a raw task and routes each piece to a
real, currently-registered capability, reasoning over a live index
(Capability Registry) instead of a hardcoded list. Planner itself runs
through Phase 5's shared Reasoning Engine, the same "configuration over
shared infrastructure" pattern every agent has followed since Odoo Agent
— its capability declaration and prompt template live in
`services/agents/agents/planner/`, not here.

Phase 30 added `planning/workflows/` — saved, re-triggerable multi-agent
flows (YAML, reusing this same `TaskGraph`/`Subtask` schema) instead of
Planner's own one-shot dynamic decomposition. See
`docs/aios-architecture-and-phases.md`'s Phase 30 section for the full
design rationale (the core discovery: this system has never had a
background dispatcher anywhere, so dispatch/advance are explicit calls,
never an ambient poller).

## Run it

```bash
pip install -r requirements.txt
export SECURITY_LAYER_URL=http://localhost:8000
export AGENTS_URL=http://localhost:8005     # Capability Registry syncs from here; Planner calls back into it
export PLATFORM_URL=http://localhost:8002    # real Task Manager subtasks land here
export WORKFLOWS_DIR=$(pwd)/../../workflows  # Phase 30: real *.yaml workflow definitions, no default
uvicorn main:app --port 8008
```

Trigger a real, saved workflow (Phase 30):

```bash
curl -X POST localhost:8008/workflows/code_review_pipeline/trigger
curl localhost:8008/workflows/runs/<task_graph_id>
curl -X POST localhost:8008/workflows/runs/<task_graph_id>/advance   # after a paused step's approval is decided
```

Capability Registry doesn't auto-sync on startup (unlike template
registration in earlier phases) — call it once agents exist to discover:

```bash
curl -X POST localhost:8008/capabilities/sync
```

A capability seen for the first time registers immediately (it's just
reflecting an agent that already shipped and was code-reviewed). A
capability whose scope actually *changed* from its last-synced version
creates a pending entry requiring real governance approval — same
pattern as template versioning:

```bash
curl -X POST localhost:8000/approval/<approval_id>/decide -d '{"decided_by":"human_admin","approve":true}'
curl -X POST localhost:8008/capabilities/reconcile-approvals
```

## Test it

```bash
pytest tests/test_capability_store.py tests/test_graph_builder.py -q   # no live dependencies

SECURITY_LAYER_URL=http://localhost:8000 AGENTS_URL=http://localhost:8005 PLATFORM_URL=http://localhost:8002 \
pytest tests/ -v   # full suite against the live stack + live Ollama
```

38 tests, all passing against real Postgres (genuine `TIMESTAMPTZ`
columns, confirmed via direct schema inspection, under a non-UTC
session), a real live 3-capability roster (`odoo_agent`, `database_agent`,
`planner` itself), and a real live model producing an actual routed plan.
`tests/test_phase30_workflows.py` (11 of the 38) covers the real,
checked-in `code_review_pipeline.yaml` — synchronous full-chain dispatch,
a paused-step case proving dependents correctly stay `"planned"` rather
than being batch-dispatched, `advance()` resuming an approved step and
dispatching what it newly unblocks in the same call, `advance()` on a
still-undecided approval being a verified no-op, and one genuine live
trigger of the real workflow against real capability executions.

## Real bugs found by live testing, not the test suite

- **`delegate_to` and Planner's own `task_graph` collided.** The shared
  6-field output schema's `delegate_to` field (Phase 4/5) means "hand
  this single task to one other capability" — a real, reasonable
  instruction for an individual agent, and a live model applied it to
  Planner too, since nothing said not to. Reasoning Engine's routing
  checks `delegate_to` first, unconditionally, so this silently
  discarded a perfectly good `task_graph` in favor of a generic
  single-capability handoff. Fixed at the template AND the code level —
  Planner's own template now explicitly says never to set `delegate_to`,
  and `loop.py`'s `_decide_routing` ignores it for `agent_capability ==
  "planner"` regardless of what the model says, the same "don't just
  trust a prompt instruction" posture the rest of this system already
  applies to model output.
- **A live model reasonably self-assessed `risk_classification: "low"`
  for its own plan**, which routed the *entire plan* into
  `awaiting_approval` before any subtask could even be attempted —
  correct behavior for an individual agent proposing a real change, but
  wrong for Planner: producing a `task_graph` never touches real code,
  data, or systems, and each subtask already goes through its own
  independent approval gate when it actually executes. A plan needing
  human sign-off before any routing could happen would make Planner
  slower than just asking a human directly. Fixed the same way — a
  structural override in `loop.py` (`risk = "informational"` for
  `agent_capability == "planner"`, never the model's own judgment) plus
  an explicit template instruction.
- **A live model used an action name (`odoo.read_orm`) instead of the
  capability name (`odoo_agent`) as a subtask's `agent_capability`** —
  reasonable confusion given the roster text lists both together. Fixed
  by making the template's distinction between the two explicit.
- **A latent Pydantic v2 bug in Phase 5's `ExecuteRequest`**: `target_model:
  str = None` only sets a default, it does not widen the type to accept
  an explicit `null` in a JSON request body — any caller that sends
  `null` rather than omitting the field entirely got a 422, even though
  the field is meant to be optional. Every prior caller happened to omit
  the field; Planner's own client was the first to send it explicitly.
  Fixed at the source (`Optional[str] = None`) plus made this service's
  own HTTP client omit unset optional fields rather than send `null`, a
  more robust general habit regardless of whether a given receiving
  model happens to be written correctly for it.

## What's real

- **Capability Registry aggregates from a real live source, not a
  copy that can drift**: `GET /capabilities` on the agents service is
  the same data Reasoning Engine's own `local_precheck` actually
  enforces — confirmed live, the synced entry's `allowed_actions` match
  `capability.yaml`'s real content exactly.
- **Scope-change versioning is genuinely approval-gated**: confirmed
  live, a capability whose `allowed_actions` changed from its last-synced
  version creates a `pending_approval` entry, the OLD scope stays active
  and enforced until a real governance approval resolves, and only then
  does the new version supersede it — the same "no drift between preview
  and what's live" discipline as Phase 7's dry-run/write matching.
- **Planner's fail-closed precondition is real**: if Capability Registry
  is unreachable, Reasoning Engine never even calls the model for a
  `planner` execution — confirmed by reading the code path, the registry
  fetch happens and is checked before context building starts.
- **The live roster genuinely drives routing, not a hardcoded prompt
  list**: confirmed live across the same running system — an Odoo-domain
  question routed to `odoo_agent`, and after Database Agent's own
  `capability.yaml` changed test-to-test, the SAME Planner template
  (unedited) reasoned over the new roster correctly, because the
  roster is injected as data, never baked into the prompt text.
- **Task graph → real Task Manager subtasks, not local bookkeeping**:
  confirmed live, `POST /planner/plan`'s subtasks each have a real
  `platform_task_id`, independently verified by fetching that task back
  from `platform-spine` directly.
- **Replanning genuinely supersedes rather than replacing**: confirmed,
  a re-plan creates a new `task_graph` row and marks the old one's
  `superseded_by` — both remain queryable, so "why was this restructured"
  stays answerable, per the Phase 8 doc's logging requirement.
- **(Phase 30) A saved workflow dispatches through the exact same
  governance-gated `execute_reasoning()` call as every non-workflow
  execution** — confirmed live, a step's own capability role grant is
  what authorizes it, not a workflow-level bypass; there is no code path
  that pre-answers or skips a step's own gate.
- **(Phase 30) `advance()` is genuinely safe to call speculatively at any
  time** — confirmed live and by test, calling it before a paused step's
  approval has been decided is a verified no-op (mirrors
  `reasoning_engine/loop.py`'s own `resume()` semantics), and calling it
  after approval both flips that step to `"done"` and dispatches
  whatever it unblocks in the same call.

## What's a stub or simplified

- **Planner reasons at a fixed local-model classification ceiling**, not
  a genuine per-human clearance level. The Phase 8 doc calls for Planner
  to reason "at the requesting human's own classification level" — this
  system has no per-human identity/clearance concept anywhere yet (Phase
  2's auth is a stub token→role file), so there's nothing real to key
  that off of. Using the same local-model ceiling every other agent gets
  is the closest honest approximation available today; a real
  implementation needs Phase 2's auth to grow real identities first.
- **No parallel subtask execution** — explicitly out of scope per the
  Phase 8 doc; Task Manager still walks `depends_on` effectively
  sequentially.
- **Live-model routing between two plausible capabilities isn't
  deterministic** (e.g. "how many sale orders does X have" could
  reasonably go to either `odoo_agent` or `database_agent`) — this is
  live-model judgment, not a routing bug; the mechanism (real roster,
  real subtask creation, real dependency tracking) is what's verified,
  not that a small local model always makes the objectively best call.
- **(Phase 30) No workflow-runs view in the web UI.** `web/` has no page
  that lists tasks generically — `Approvals.tsx` already surfaces any
  workflow step paused `awaiting_approval` (same `/approval/pending`
  endpoint every other execution uses), but there is no dedicated
  timeline for a workflow *run* as a whole.
- **(Phase 30) Approving a step in Control UI does not auto-continue its
  workflow.** This compounds a Phase 24 gap named honestly at the
  time: `decide_approval()` never called `loop.resume()` for any single
  execution, and it still doesn't call the new `/workflows/runs/{id}/advance`
  for a workflow step either. An operator, IDE, or script must call it
  explicitly.
- **(Phase 30) No workflow definition versioning.** A `*.yaml` file
  changing on disk changes every future trigger immediately — unlike
  `assembly`'s prompt templates or Capability Registry entries, there is
  no version history or approval gate on the workflow definition itself,
  only on what each dispatched step's own capability does.

## Next

Phase 9: Documentation Engine + ERP Knowledge Engine — every agent built
so far, and Planner itself, has been reasoning over placeholder cached
schema and business memory rather than real ingested documentation.
Feeding Vector Search properly matters more at this point than adding
another agent that would face the same knowledge gap.
