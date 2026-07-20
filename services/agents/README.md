# Phase 5/7/8/10/14/15/16 — Reasoning Engine + fifteen agents (working implementation)

Real, tested code. This is the first phase that actually calls a model:
Reasoning Engine is the shared execution loop every agent runs through.
Odoo Agent (Phase 5), Database Agent (Phase 7), Planner (Phase 8), Django
Agent, DevOps Agent, Docker Agent, Testing Agent (Phase 10), Costing
Agent, Accounting Agent, Inventory Agent (Phase 14), and now
Manufacturing Agent, Sales Agent, and Project Management Agent (Phase
15) all run on it — each a thin capability declaration
(`capability.yaml`) plus a prompt template (`template.md`), not a
bespoke service of its own. Database Agent also needed Reasoning Engine
to gain a small, explicitly-scoped tool-call mechanism
(`database_bridge.py`) for its mandatory dry-run-before-write pattern —
the first time this loop calls back out mid-reasoning rather than just
parsing one response and routing. Planner needed a fail-closed
precondition (no model call at all if Capability Registry is
unreachable) and a code-level override on two of the shared schema's
fields (`delegate_to`, `risk_classification`) whose generic meaning
turned out not to apply to a capability whose job is deciding how work
is routed, not doing the work itself. Phase 10's four agents needed no
new infrastructure at all — `execution_bridge.py` and
`database_bridge.py` were already generic enough to reuse unchanged for
their `propose_*` actions, and the only genuinely new mechanism
(`shell_bridge.py`) is a small tool-call extension of the same pattern
`database_bridge.py` established, for Docker Agent's read-only
`docker.inspect` and Testing Agent's `testing.run_suite`. Phase 14's
three business agents pushed that reuse even further: Inventory Agent's
propose actions reuse `database_bridge.materialize_propose_write`
completely unchanged (a *second* agent on the exact dry-run-then-write
path Database Agent established), Accounting Agent's `propose_entry`
reuses `execution_bridge.materialize_propose_change` unchanged, and the
one genuinely new bridge this batch needed (`erp_bridge.py`, for Costing
Agent's `propose_formula_change`) is a thin ~15-line wrapper around ERP
Knowledge Engine's already-existing, already-approval-gated formula
registration (Phase 9) — no new write mechanism invented for it.

Phase 15's three agents push reuse further still: all four of the
batch's `propose_*` actions (`manufacturing.propose_schedule_change`,
`sales.propose_quote`, `sales.propose_order_change`,
`pm.propose_milestone_update`) reuse
`execution_bridge.materialize_propose_change` completely unchanged —
zero new materialization code for any of them. The one genuinely new
tool-call bridge (`task_bridge.py`, for Project Management Agent's
`task.read`) mirrors `database_bridge.py`/`shell_bridge.py`'s exact
shape: a non-terminal action that fetches Task Manager's real task
snapshot *and* its real, ordered transition history (a genuine gap this
phase closed — `platform_spine/task_manager/store.py`'s `task_events()`
had existed since Phase 2 but was never reachable over HTTP until this
phase added `GET /api/v1/tasks/{task_id}/events`) and feeds it back into
context. Sales Agent's `explain_status` is the first tool call to use a
genuinely new dimension on Database Connector (Phase 7) itself: customer
PII (`res_partner.email`) is now excludable independently of
`classification_ceiling`, never inferred or defaulted to "all," always
named explicitly per task via a new `pii_fields_requested_json` field —
see `services/database/README.md`'s own Phase 15 section for the
mechanism, and this service's "Real bugs found by live testing" section
below for a genuine live bug that mechanism's own first end-to-end test
run surfaced.

Phase 16's three code-quality agents (Code Review, Reverse Engineering,
Architecture) are the Coding Brain's first real batch — a deliberate
pivot after five straight ERP-brain phases. Architecture Agent needed no
new mechanism at all: Database Agent's own template has said `delegate_to
"architecture_agent" if you recognize one` since Phase 7, written when
Architecture Agent didn't exist yet, so building it now makes that
delegation resolve to something real for the first time with zero
changes to Database Agent's own template, and `architecture.propose_decision`
reuses `execution_bridge.materialize_propose_change` unchanged. Reverse
Engineering Agent's `propose_documentation_draft` reuses the same git
bridge for its commit half, then chains into the one genuinely new
bridge this phase needed (`reverse_eng_bridge.py`) to ingest that SAME
just-committed file into Documentation Engine's already-existing `POST
/docs/ingest` (Phase 9) — a confirmed-accurate reconstruction becomes
real, independently-queryable documentation, not a second copy sitting
in this service's own output table. Code Review Agent is the first agent
whose own actions never require human approval at all (its output is
advisory) but whose assessment can attach to ANOTHER agent's pending
approval via a new governance mechanism
(`services/governance/README.md`'s Phase 16 section) — `review_bridge.py`
gives it two real tool calls (a real `git diff` via Git Manager, a real
call-graph lookup via Code Analysis Engine) mirroring `database_bridge.py`'s
exact shape.

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
# Optional — closes the Phase 14 loop: an approved costing.propose_formula_change
# actually calls ERP Knowledge Engine's real formula registration.
export KNOWLEDGE_PIPELINES_URL=http://localhost:8009
# Optional — Phase 12: where a plugin's approved capability.yaml gets
# discovered from. Must match services/extensibility's own env var of
# the same name.
export PLUGIN_CAPABILITIES_DIR=/tmp/ai_os_plugins
uvicorn main:app --port 8005
```

On startup this service auto-loads every `agents/<name>/capability.yaml`
it finds (currently `odoo_agent`, `database_agent`, `planner`,
`django_agent`, `devops_agent`, `docker_agent`, `testing_agent`,
`costing_agent`, `accounting_agent`, `inventory_agent`,
`manufacturing_agent`, `sales_agent`, `project_management_agent`,
`code_review_agent`, `reverse_engineering_agent`, and `architecture_agent` —
plus any Phase 12 plugin capabilities under `PLUGIN_CAPABILITIES_DIR`,
see `services/extensibility/README.md`) into its own DB, and best-effort
attempts to register each agent's prompt template with Prompt Builder.
Template registration is approval-gated through governance (same as
every other template) — a human still has to approve it once via
governance's `/approval` endpoints before any of them can actually run:

```bash
curl -X POST localhost:8005/odoo_agent/register       # check/retry registration
curl -X POST localhost:8005/database_agent/register
curl -X POST localhost:8005/planner/register
curl -X POST localhost:8005/django_agent/register
curl -X POST localhost:8005/devops_agent/register
curl -X POST localhost:8005/docker_agent/register
curl -X POST localhost:8005/testing_agent/register
curl -X POST localhost:8005/costing_agent/register
curl -X POST localhost:8005/accounting_agent/register
curl -X POST localhost:8005/inventory_agent/register
curl -X POST localhost:8005/manufacturing_agent/register
curl -X POST localhost:8005/sales_agent/register
curl -X POST localhost:8005/project_management_agent/register
curl -X POST localhost:8005/code_review_agent/register
curl -X POST localhost:8005/reverse_engineering_agent/register
curl -X POST localhost:8005/architecture_agent/register
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
PHASE9_PATH=/path/to/services/knowledge_pipelines \
DEMO_ERP_DATABASE_URL=postgresql://user:pass@host:5432/demo_erp \
pytest tests/ -v   # full suite against the live 8-service stack + live Ollama
```

69 tests, all passing against real Postgres (genuine `TIMESTAMPTZ`
columns, confirmed via direct schema inspection, under a deliberately
non-UTC session) and a real live Ollama model — not mocked, except for
deliberately-stubbed tests (see below) used specifically where live-model
phrasing would make a test non-deterministic without changing what's
actually being verified. `tests/test_phase10_agents.py` (Phase 10)
covers all four new agents: capability-registry boundaries, both
propose-action bridges against a real disposable Git repo, the
`shell_bridge.py` tool-call round trip against a real command, Testing
Agent's environment verification (both allow and deny paths, plus
fail-closed on an unregistered name), and one live-model smoke test each
for Django Agent and DevOps Agent. `tests/test_phase14_agents.py`
(Phase 14) covers all three business agents: Costing Agent's
`propose_formula_change` verified against ERP Knowledge Engine's real
`GET /erp-knowledge/formula/{id}` (not just the response Reasoning
Engine itself got back), Accounting Agent's `db.read` tool call plus its
unconditional-approval `propose_entry` materializing as a real git
document, Inventory Agent's real dry-run-then-write round trip against
the same disposable `demo_erp` target Database Agent's own tests use,
and one live-model smoke test each. `tests/test_phase15_agents.py`
(Phase 15) covers all three operations agents: Manufacturing Agent's
`flag_constraint` tool call plus its `propose_schedule_change`
materializing as a real git document, Sales Agent's `explain_status`
proven both ways (no PII field named → never sees `email`; explicitly
named and authorized → the real seeded value shows up in the model's
next-turn prompt) plus `propose_quote` materializing as a real git
document, Project Management Agent's `task.read` tool call against a
real task created and transitioned through platform-spine's Gateway
during the test itself plus `propose_milestone_update` materializing as
a real git document, and one live-model smoke test each.
`tests/test_phase16_agents.py` (Phase 16) covers all three code-quality
agents: Code Review Agent's `review.check_callers` tool call verified
against a real Code Analysis Engine scan of a real two-function repo
(confirming the actual real caller name shows up in the model's
next-turn prompt, not a placeholder), `review.fetch_diff` plus the new
attach-review mechanism proven end to end (a real diff of a real
committed branch, attached to a real OTHER pending approval, confirmed
by fetching that approval back from governance directly and confirming
its own pending status is untouched), Reverse Engineering Agent's
`propose_documentation_draft` proven to both materialize as a real git
document AND independently show up in Documentation Engine's own
`GET /docs/sources` listing, Architecture Agent's `propose_decision`
materializing as a real git document with zero chained step (unlike
Reverse Engineering Agent), and one live-model smoke test each.

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
- **DevOps Agent's policy role was missing `shell.execute: allow`**
  (Phase 10). `git.branch`/`git.commit`/`git.push` were correctly allowed
  for `devops_agent`, but Git Manager internally routes every one of
  those through Shell Executor, which re-checks `shell.execute` for the
  *same* capability — omitting it silently denied every git action even
  though `git.*` itself was allowed. Invisible from reading
  `default.yaml` alone (every rule present looked correct); only surfaced
  by actually running `devops.propose_pipeline_change` through
  `resume()` against a live Git Manager and getting `stage: "branch"`
  back instead of `stage: "open_mr"`. Fixed by adding the same
  `shell.execute: allow` line `odoo_agent`'s role already carried for
  exactly this reason.
- **Governance's policy hot-reload (`POST /security/reload`) does not
  pick up new *routes*, only new *rules*.** Adding
  `/security/verify_environment` to `api.py` required restarting the
  governance process — reload only re-parses `default.yaml` into the
  already-running `PolicyEngine`, it doesn't re-import FastAPI's route
  table. Cost real debugging time mid-session (a live call to the new
  endpoint returned a generic `404 Not Found` indistinguishable at first
  glance from a policy denial) before the actual cause — stale process,
  not stale policy — was confirmed.
- **A real capability's permission boundary lives in more than one
  file, and Phase 14 caught two different ways of missing one of them.**
  (1) `secrets_registry.yaml`'s `demo_erp` entry only listed
  `database_agent` in its `allowed_capabilities` — a separate allow-list
  from governance's `roles:` policy, enforced by Database Connector's
  own `secrets.resolve` call. `accounting_agent`/`inventory_agent` had a
  fully correct governance role (`db.read: allow` etc.) but still got a
  real `403 Forbidden` from `/security/secrets/resolve` the first time
  Accounting Agent's `db.read` tool call actually ran. (2)
  `accounting_agent` had no
  `services/execution/execution/shell_executor/allowlists/accounting_agent.yaml`
  file at all — its governance role correctly had `shell.execute: allow`
  and every `git.*` action, but Shell Executor's own default-deny lookup
  denied with `"no command allowlist registered for 'accounting_agent'"`
  the first time `accounting.propose_entry` tried to materialize via
  Git Manager. Neither gap was visible from reading `default.yaml`
  alone — both needed an actual live call through the real dependent
  service to surface, and both are now locked in as regression tests
  (`services/governance/tests/test_secrets.py`,
  `services/execution/tests/test_allowlist.py`).

- **Phase 15: the PII gate's first version was layered on top of the
  classification ceiling instead of being genuinely independent from
  it — found by Sales Agent's own reasoning-loop test, not by reading
  the code.** `filter_columns` (ceiling) ran first, then
  `filter_pii_columns` ran as an *additional* restriction on whatever
  survived. That seemed right in isolation, but broke the actual design
  goal the moment it was exercised live: Sales Agent is deliberately kept
  at `classification_ceiling: internal` (it has no business seeing
  confidential data in general), so even an explicitly-authorized,
  explicitly-requested `email` field never got past the ceiling gate
  before the PII gate ever ran — `test_sales_explain_status_with_explicit_pii_request_gets_real_email`
  asserted a real email address would appear in the model's next-turn
  prompt and it never did. Fixed in `services/database/database/database_connector/scoping.py`:
  `filter_columns` now skips PII-tagged columns entirely (they're simply
  not a point on the public/internal/confidential scale), and
  `filter_pii_columns` is the sole, independent decision-maker for them —
  a genuinely separate dimension, not a stricter tier layered on the
  first one. Locked in as `test_pii_gate_is_independent_of_ceiling_not_layered_on_top_of_it`
  in `services/database/tests/test_scoping.py`.
- **A second, separate live bug the same test surfaced**: `database_bridge.py`'s
  `db.read` tool call never forwarded the calling agent's own declared
  `classification_ceiling` to Database Connector — every agent's tool-call
  reads silently ran at the hardcoded default (`internal`), regardless of
  what `capability.yaml` actually declared (Accounting Agent's
  `confidential` ceiling was never actually reaching Database Connector
  either, just never previously exercised against a confidential column).
  Fixed by having `loop.py` pass `cap_def.classification_ceiling` through
  to `database_bridge.handle_tool_call()`.
- **Phase 16: `review.check_callers` originally surfaced raw internal
  symbol ids instead of names — useless for a model, or a human reading
  its final assessment, to reason about.** Code Analysis Engine's own
  `GET /symbol/{ref}` (Phase 11) returns its `callers`/`callees` lists as
  raw UUIDs, not qualified names — fine for that endpoint's original
  callers (which already had the id from a prior graph query), wrong for
  a model that only knows a human-readable name. Found live: the review
  test's stubbed second turn asserted a real caller's qualified name
  (`widgets.Widget.render`) would appear in the next prompt, and instead
  found a bare UUID. Fixed by switching `review_bridge.py` to call
  `GET /graph` instead, which already resolves every edge to real
  qualified names — no change needed to Code Analysis Engine itself,
  just which of its two existing endpoints the new caller actually
  wanted.
- **A second, separate bug the same feature surfaced**: `review.fetch_diff`
  passing a bare branch name straight through to `git diff <branch>`
  compares that branch's tip to the CURRENT working tree, not to
  `main` — empty right after a clean checkout, since nothing's
  uncommitted. Fixed by building `main...{target_branch}` automatically
  in `review_bridge.py` rather than pushing git range syntax onto the
  model, which had never needed to know it before.

## What's real

- **Phase 13 addition:** `GET /reasoning/executions` (optional
  `status`/`agent_capability` filters) — no listing endpoint existed
  before this, only single-execution lookup by id. Backs
  Observability's reasoning-iterations-per-task metric and its
  stuck-past-`max_iterations` gap check (a completed execution whose
  `failure_reason` starts with `iteration_limit_exceeded` — Reasoning
  Engine's loop is synchronous, so there's no separate "still running"
  status to poll the way a background job would have).
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
- **Phase 10's four new agents needed zero Reasoning Engine dispatch
  logic beyond a set membership check.** `django.propose_migration`,
  `devops.propose_pipeline_change`, `devops.propose_infra_change`,
  `docker.propose_compose_change`, and `testing.propose_new_test` all
  reuse `execution_bridge.materialize_propose_change()` and
  `database_bridge.materialize_propose_migration()` completely unchanged —
  confirmed live, not just by inspection: `test_django_propose_migration_reaches_the_real_migration_adapter`
  and `test_devops_propose_pipeline_change_materializes_as_real_branch_commit_push`
  drive an approved execution through `resume()` and land a real
  migration-adapter call / real branch+commit+push respectively, with no
  agent-specific code in either bridge.
- **Planner requires zero code changes to route to any of the four new
  agents**, confirmed live rather than just by architecture: after
  `POST /capabilities/sync` on Phase 8's Capability Registry, a live
  Planner call asking to "explain the CI/CD pipeline" produced a
  `task_graph` routing to `devops_agent`, and a "report test coverage"
  question routed to `testing_agent` — the exact claim the Phase 10 doc
  makes in Section 1.
- **Testing Agent's environment verification is a real, structural gate,
  not policy convention** (Phase 10, Section 5): `shell_bridge.py` calls
  Security Layer's `POST /security/verify_environment` *before* every
  `testing.run_suite` tool call, and a denial there means the shell
  command is never even attempted — confirmed live for three cases: a
  registered sandbox (`test_sandbox_1`, runs for real), a registered
  non-sandbox (`production_erp`, denied, audited, never executes), and an
  unregistered name (denied identically — fail-closed, not "assumed
  safe because it isn't explicitly marked unsafe").
- **`docker.inspect` and `testing.run_suite` are genuine tool calls, not
  agent self-reports** (`shell_bridge.py`, mirroring `database_bridge.py`'s
  `db.read` pattern): the model's declared command actually runs via
  Shell Executor, and the real stdout is fed back into the *next* turn's
  prompt — confirmed live by asserting the exact real output (a real git
  commit message) is absent from the first turn's prompt and present on
  the second.
- **Phase 14's three business agents pushed bridge reuse further than
  any prior batch — two of the three needed literally zero new
  materialization code.** Inventory Agent's `propose_adjustment`/
  `propose_reorder` reuse `database_bridge.materialize_propose_write()`
  — the SAME dry-run-then-write path Database Agent established in
  Phase 7, now genuinely exercised by a second, independent agent's own
  policy role and capability boundary, confirmed live with a real write
  landing in the disposable `demo_erp` database and rolling back
  cleanly on the fixture's teardown. Accounting Agent's `propose_entry`
  reuses `execution_bridge.materialize_propose_change()` — confirmed
  live with a real branch/commit/push, deliberately never touching
  `database_bridge` at all, matching the Phase 14 doc's explicit
  conservatism for this one agent (no direct ledger write path exists
  for it to reuse).
- **The one genuinely new bridge this batch needed
  (`erp_bridge.py`, for Costing Agent's `costing.propose_formula_change`)
  is real, not a stub returning a canned success** — confirmed live: an
  approved formula change reaches ERP Knowledge Engine's actual
  `POST /erp-knowledge/formula/register` (Phase 9), and the resulting
  record is independently verified by fetching it back via that
  service's own `GET /erp-knowledge/formula/{id}`, not by trusting
  Reasoning Engine's own report of what happened.
- **Planner requires zero code changes to route to any of the three new
  business agents either**, confirmed live the same way Phase 10's
  claim was: after a `POST /capabilities/sync`, a live Planner call
  asking to "have Costing Agent explain how the standard costing
  formula works" produced a `task_graph` routing to `costing_agent`. One
  live run first came back `no_capability_found` on a more ambiguous
  phrasing of the same question — an accepted instance of the
  small-model phrasing variance already documented for Planner in
  `services/planning/README.md`, not a wiring issue; a second, more
  direct phrasing routed correctly, and the routing mechanism itself
  (Capability Registry lookup, task_graph construction) is unchanged
  code exercising it, not new code written to make this particular
  question work.

- **All four of Phase 15's `propose_*` actions materialize as real git
  documents, confirmed live** — `manufacturing.propose_schedule_change`,
  `sales.propose_quote`, `sales.propose_order_change`, and
  `pm.propose_milestone_update` each reuse
  `execution_bridge.materialize_propose_change()` completely unchanged;
  each is confirmed with a real branch/commit/push landing in a
  disposable repo, verified by reading `git show` directly rather than
  trusting the returned status.
- **`manufacturing.flag_constraint`'s real stock/capacity check is a
  genuine tool call**, not a guess dressed up as one — the exact same
  `db.read` mechanism Database Agent/Accounting Agent/Inventory Agent
  already use, confirmed live against real seeded `demo_erp` data.
- **Sales Agent's PII-scoped `sales.explain_status` is real, live,
  minimum-necessary-by-default behavior, confirmed both directions**:
  a task that doesn't name a PII field never sees `email` even though
  Sales Agent is fully authorized in principle
  (`test_sales_explain_status_without_pii_request_never_sees_email`), and
  a task that genuinely needs it and names it explicitly gets the real
  seeded value back (`test_sales_explain_status_with_explicit_pii_request_gets_real_email`)
  — confirmed by asserting the real email address is present in the
  model's second-turn prompt, not just that the API call succeeded.
- **Project Management Agent's `task.read` tool call is real, not a
  self-report**: `task_bridge.py` calls platform-spine's Gateway over
  real HTTP for both the task snapshot and (Phase 15's own gap-fill)
  its real ordered event history — confirmed live by creating a real
  task, transitioning its status once for real, then asserting the
  agent's second-turn prompt contains the real `in_progress` status and
  the real transition detail text, not anything the model invented.
- **Code Review Agent's two tool calls are genuine, not agent
  self-reports**: `review.fetch_diff` runs a real `git diff` via Git
  Manager against a real committed branch (confirmed by asserting the
  actual changed filename shows up in the next prompt, not before);
  `review.check_callers` looks up a real call graph produced by a real
  Code Analysis Engine scan of a real two-function repo (confirmed the
  real caller's qualified name — not a placeholder, not a guess —
  appears in the next prompt).
- **The attach-review mechanism closes end to end, confirmed live, not
  just unit-tested in isolation**: a real OTHER agent's pending approval
  (created exactly the way any propose_* action's `require_approval`
  outcome would create one) gets a real review attached by Code Review
  Agent's own completed execution, and that approval's own `pending`
  status is confirmed unchanged by fetching it back from governance
  independently — the review is additive context, never a vote,
  confirmed by observation rather than by reading the code that says so.
- **Reverse Engineering Agent's confirmed draft becomes real,
  independently-queryable documentation, not just a git-committed
  file** — confirmed live: after `resume()` materializes the git commit,
  the SAME file gets ingested via Documentation Engine's real
  `POST /docs/ingest`, and the resulting document shows up in that
  service's own `GET /docs/sources` listing, verified independently
  rather than by trusting Reasoning Engine's own report of what happened.
- **Architecture Agent needed zero new code to become a real delegate
  target** — confirmed live: `database_agent`'s own template already
  said `delegate_to "architecture_agent" if you recognize one` since
  Phase 7, unchanged this phase; building Architecture Agent is the only
  change needed for that delegation to actually resolve to something.

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
- **Django Agent's `django.explain_structure` and DevOps Agent's
  `devops.explain_topology` still only see whatever Documentation
  Engine (Phase 9) has ingested**, per the Phase 10 doc's explicit
  `known_limitation` — no live source-code analysis until Code Analysis
  Engine (Phase 11) exists.
- **`docker.inspect` and `testing.run_suite` were verified against `git`
  and `echo`, not real `docker`/`pytest` binaries** — this environment
  has neither installed nor on Shell Executor's minimal safe-env `PATH`
  (same class of constraint already documented in
  `services/execution/README.md` for `DockerSandbox`). The tool-call
  wiring itself — real command out, real result back into the next
  turn's prompt — is genuinely verified; a real `docker`/`pytest`
  installation would need no code change here, only allowlist entries
  that already exist in `docker_agent.yaml`/`testing_agent.yaml`.
- **Deployment execution for DevOps Agent is out of scope by design**,
  not a placeholder for something half-built — the Phase 10 doc defers
  it to its own future phase, the same way real database writes got
  Phase 7 rather than riding along with Phase 6.
- **`demo_erp` has no literal stock table** (only `sale_order` and
  `res_partner` — no live Odoo instance in this environment, same
  constraint every phase since 7 has documented), so Inventory Agent's
  dry-run-then-write test reuses `sale_order` the same way Database
  Agent's own Phase 7 tests do. What's genuinely proven is the WIRING —
  inventory_agent's own policy role and capability boundary driving the
  real dry-run-then-write path end to end — not literal inventory
  semantics against a real warehouse schema.
- **Costing/Accounting/Inventory Agent's `explain`/`calculate`/
  `read_ledger` actions reason over whatever's already in retrieved
  context** (Vector Search content, prior tool-call results this turn) —
  none of them have a dedicated formula- or ledger-specific retrieval
  mechanism beyond what Context Builder already assembles generically
  for every agent.
- **Manufacturing/Sales/PM Agent's `explain`/`flag`-style actions reason
  over whatever's already in retrieved context or a real tool-call
  result this turn** — same posture as Phase 14's business agents, no
  dedicated workflow- or milestone-specific retrieval mechanism beyond
  what Context Builder already assembles generically for every agent.
- **Project Management Agent's ERP-project-status half is
  documentation-only** — no live Odoo project-management module exists
  in this environment (`demo_erp`'s minimal seeded schema has no project
  table), so `pm.explain_status` for a customer-facing project draws on
  whatever ERP Knowledge Engine (Phase 9) has ingested, never a live
  query. Its task-history half (`task.read`) IS a real, live query —
  see "What's real" below.
- **The PII registry (`pii_registry.yaml`) is scoped to exactly the one
  PII-shaped column that exists in this environment's minimal seeded
  schema** (`res_partner.email`) — not a general PII taxonomy, per the
  Phase 15 doc's own explicit out-of-scope note. Structurally ready to
  extend to more columns via the same registry file the moment a real
  schema has more of them.
- **Code Review Agent is not automatically triggered by any other
  agent's own propose/resume flow** — a deliberate Phase 16 scope
  decision (the doc's own Section 0), not a placeholder for something
  half-built. It's invoked directly (by a human, or a future
  orchestration layer) against a specific branch and, optionally, an
  existing pending approval to attach its assessment to. Wiring it into
  every prior phase's own materialization path automatically is real,
  separately-scoped future work.
- **Reverse Engineering Agent's "confirmed accurate" step in "confirmed
  drafts feed back as real documentation" is a human decision made at
  approval time**, not a structural confidence check this system runs
  itself — the agent's own prompt discipline (label everything as
  inferred/reconstructed) plus the existing human-approval gate on
  `propose_documentation_draft` are what stand between a plausible-
  sounding guess and something Documentation Engine treats as real.

## Next

Phase 17: Engineering & Calculation Agents (`calculation_agent`,
`cutlist_optimization_agent` — Manufacturing Agent's already-named future
delegate target from Phase 15). Phase 18: Cross-Cutting Agents (Security
Agent, Research Agent) — natural next consumers of this phase's new
approval-review attachment mechanism. Phase 24 (Control UI) is also now
designed (`docs/phase-24-control-ui.md`) and could be prioritized instead
once operator-facing UI work is ready to start.
