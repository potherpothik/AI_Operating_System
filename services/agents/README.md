# Phase 5/7/8/10/14/15/16/17/18/22/23/25/26/27/28 — Reasoning Engine + twenty-three agents + Model Router + MCP client wiring + OpenAI shim's raw model access + adapter contracts/registry (working implementation)

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

Phase 17's three agents (Calculation, Cutlist Optimization, AutoCAD)
share one integrity principle: none of them let the model assert a
numeric or layout result from its own generation. Every real number or
layout comes from an actual deterministic script — `eval_formula.py` (a
restricted `ast`-based arithmetic evaluator, structurally incapable of
calling a function or importing anything, regardless of what expression
string reaches it — never Python's own `eval()`), `cutlist_solver.py` (a
real first-fit-decreasing bin-packing heuristic), and `dxf_parse.py` (real
`ezdxf`-based DXF structure extraction) — executed via Shell Executor's
existing sandbox (Phase 6), the same real subprocess path `shell_bridge.py`
already established, just against a fixed, reviewed script instead of a
model-chosen command. `calc_bridge.py`, `cutlist_bridge.py`, and
`autocad_bridge.py` are three small new tool-call bridges, all following
the same shape. Calculation Agent surfaced one genuine gap in ERP
Knowledge Engine (Phase 9/14): `store.get_active_formula_by_name()` has
existed since Phase 14 (used internally when registering a new formula
version) but was never reachable over HTTP until a model needed to
resolve a real formula by name — `GET /erp-knowledge/formula/by-name/{name}`
closes it. AutoCAD Agent's `propose_annotation` reuses
`execution_bridge.materialize_propose_change` unchanged, same as every
other `propose_*` action.

Phase 18's four agents (Python, Documentation, Security, Research) are
mostly config, exactly as `CLAUDE.md` predicted before any of them were
built. Python Agent needed nothing new — its own template actively
checks whether a request is really Odoo- or Django-specific and
delegates rather than defaulting to a generic answer. Documentation
Agent's `docs.propose_new_doc` reuses Phase 16's `reverse_eng_bridge.py`
chained docs-ingest step completely unchanged for a second agent — the
first real confirmation that bridge generalizes past the one agent it
was written for. Research Agent's `propose_external_lookup` materializes
as a plain reviewable document, honestly never an actual fetch — this
system has no external web-access tool anywhere in its history, by
design. Security Agent needed the one genuinely new piece:
`security_bridge.py` gives it a real, non-terminal `security.audit_query`
tool call against governance's actual Audit Logger (Phase 1), which
surfaced one small, real gap — `GET /audit/query` only ever supported
`actor_id`/`action` filters, no `correlation_id`, the standard way this
system already threads one task's related events together. Closed with
one new optional filter on the existing endpoint.

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
# Optional — closes the Phase 17 loop: Calculation/Cutlist/AutoCAD
# Agents' real sandboxed scripts (eval_formula.py, cutlist_solver.py,
# dxf_parse.py). Without it, calc.apply_formula/cutlist.run_optimizer/
# autocad.explain_drawing all report not_configured rather than guessing
# a path — must point at the real absolute path to
# services/execution/execution/shell_executor/scripts/ on shared storage
# (same "real local path, single-host dev convention" PROPOSAL_REPO_PATH
# already uses). The interpreter that ACTUALLY runs these scripts is
# whichever `python3` resolves on Shell Executor's own PATH — activate
# that service's venv before running it, or ezdxf (needed by
# dxf_parse.py) won't be importable even though it's in requirements.txt.
export CALC_SCRIPTS_DIR=/home/you/AI_Operating_System/services/execution/execution/shell_executor/scripts
uvicorn main:app --port 8005
```

On startup this service auto-loads every `agents/<name>/capability.yaml`
it finds (currently `odoo_agent`, `database_agent`, `planner`,
`django_agent`, `devops_agent`, `docker_agent`, `testing_agent`,
`costing_agent`, `accounting_agent`, `inventory_agent`,
`manufacturing_agent`, `sales_agent`, `project_management_agent`,
`code_review_agent`, `reverse_engineering_agent`, `architecture_agent`,
`calculation_agent`, `cutlist_optimization_agent`, `autocad_agent`,
`python_agent`, `documentation_agent`, `security_agent`, and `research_agent` —
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
curl -X POST localhost:8005/calculation_agent/register
curl -X POST localhost:8005/cutlist_optimization_agent/register
curl -X POST localhost:8005/autocad_agent/register
curl -X POST localhost:8005/python_agent/register
curl -X POST localhost:8005/documentation_agent/register
curl -X POST localhost:8005/security_agent/register
curl -X POST localhost:8005/research_agent/register
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

118 tests (114 as of Phase 27; 87 as of Phase 18, growing with Phase
22/23/26/27/28's own test files — `test_phase22_agent.py`, `test_phase23_model_router.py`,
`test_phase26_mcp_bridge.py`, `test_phase27_openai_shim.py`,
`test_phase28_adapter_registry.py`, `test_adapter_boundary.py`), all
passing against real Postgres (genuine `TIMESTAMPTZ` columns, confirmed
via direct schema inspection, under a deliberately non-UTC session) and
a real live Ollama model — not mocked, except for deliberately-stubbed
tests (see below) used specifically where live-model phrasing would
make a test non-deterministic without changing what's actually being
verified. `test_adapter_boundary.py` (Phase 28) is a real, static AST
scan — not regex, not a convention documented and hoped for — that
fails if any module under `agents/` outside three allowlisted adapter
modules (`clients.py`, `model_router.py`, `ollama_adapter.py`) imports
`httpx`/`requests` directly; confirmed to actually catch a violation
(a throwaway test file), not just pass vacuously.
`test_phase28_adapter_registry.py` covers the new `GET /reasoning/adapters`
endpoint: real, live `is_configured()` status per model provider
(`ollama: true`, the three cloud providers genuinely `false`), plus the
real tool-adapter and IDE-surface listings. `test_phase27_openai_shim.py` (Phase 27) covers the new
`/reasoning/available_models`, `/reasoning/raw_generate`, and
`/reasoning/raw_generate_stream` endpoints against a real live Ollama
instance: real generation with real, non-zero token-usage counts from
Ollama itself, a real streamed response confirmed to arrive as genuine
incremental deltas (not one chunk pretending to stream), and a clean
404 for a model name that plainly isn't pulled rather than a silent
fallback. `test_phase26_mcp_bridge.py` (Phase 26) reuses
`services/extensibility/tests/conftest.py`'s own real
stub-MCP-server pattern (mirrored into this service's own `conftest.py`
as `stub_mcp_server`, a genuine `http.server.HTTPServer`): register and
activate a real MCP server through extensibility's real endpoints, then
confirm `research_agent`'s `research.invoke_mcp_tool` genuinely dispatches
through `mcp_bridge.py` and the real tool result folds back into the
reasoning loop, plus an honest-failure test for an unregistered server
name. `tests/test_phase10_agents.py` (Phase 10)
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
`tests/test_phase17_agents.py` (Phase 17) covers all three engineering
agents: Calculation Agent's `calc.apply_formula` verified against a real
formula registered through ERP Knowledge Engine's real approval flow
during the test itself, confirming the exact real computed number (not
a model guess) shows up in the next-turn prompt, plus a structural test
confirming an unresolvable formula name never reaches `completed` —
the agent exhausts its iteration budget rather than fabricating a
result. Cutlist Optimization Agent's `cutlist.run_optimizer` verified
against `services/execution/tests/test_calc_scripts.py`'s exact known
packing case, confirming the real `bins_used`/algorithm name show up in
the next-turn prompt and that the finalizing turn genuinely requires
approval. AutoCAD Agent's `explain_drawing` verified against a real
generated DXF file (real layers, real text, real geometric extents all
showing up in the next prompt) plus `propose_annotation` materializing
as a real git document, and one live-model smoke test each.
`tests/test_phase18_agents.py` (Phase 18) covers all four cross-cutting
agents: Python Agent's `propose_change` materializing as a real git
document, Documentation Agent's `propose_new_doc` proven to both
materialize AND independently show up in Documentation Engine's own
`GET /docs/sources` listing — the same chained-ingest proof Phase 16's
own test used, now for a second agent reusing the identical bridge
unchanged. Security Agent's `audit_query` verified against a real audit
trail written the same way any other service already writes into it
(two real events under a known `correlation_id`, both actions genuinely
present in the model's next-turn prompt). Research Agent's
`propose_external_lookup` confirmed to require approval unconditionally
— it fires even at a self-assessed `risk_classification="low"`, matching
the doc's own "external access is opt-in, never default" framing — and
materializes as a real git document. One live-model smoke test each.

## Real bugs found by live testing, not the test suite

- **`default_local_model: qwen-coder` was never actually pulled in this
  environment — a real config value nothing had ever checked (Phase 23).**
  `default_local_model`/`fallback_local_model` have existed in
  `reasoning_engine.yaml` since Phase 2, but every single live-model test
  across every phase this session only ever worked because it explicitly
  overrode `target_model` to `qwen3.5:4b` (the one model genuinely pulled
  here) — the config default silently went unused the entire time. Found
  by building `model_router.py`'s `has_model()` check and pointing it at
  the real config: `OllamaProvider().has_model("qwen-coder")` returns
  `False`, confirmed directly against this environment's real `GET
  /api/tags`. Fixed by making `loop.py`'s `execute()` call
  `model_router.resolve_model()` for the `target_model=None` path — it
  tries `default_local_model` first, genuinely checks whether it's
  available, and falls through to `fallback_local_model` for real. A live
  end-to-end run (`target_model=None`, config naming the unavailable
  `qwen-coder` as default) confirmed the execution's persisted
  `target_model` really ended up `qwen3.5:4b`, not the configured-but-dead
  default.
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
- **Phase 17: a literal JSON example in Calculation Agent's own prompt
  template broke prompt rendering for every task, not just formula
  ones** — Prompt Builder's `render()` (`services/assembly`) calls Python's
  `str.format()` on the raw template body to substitute `{task_description}`/
  `{context}`/etc.; a template author writing a plain-language example
  like `` `{"base_cost": 420}` `` in prose gets the same treatment,
  and `.format()` tried to resolve `"base_cost"` as a field name,
  raising a real `500` on every single render. Found live, not by
  reading the code — invisible from the template file alone, since
  nothing about it looks like code. Fixed by escaping the literal braces
  (`{{`/`}}`, the standard `str.format()` escape) in
  `calculation_agent/template.md`; every other agent's template was
  checked and had no literal braces to begin with. Worth remembering for
  any future template that wants to show a JSON example in its own
  prose.
- **Not a code bug, but a real operational gotcha this phase's own
  scripts exposed**: `dxf_parse.py` needs `ezdxf` importable by whichever
  `python3` Shell Executor's sandboxed subprocess actually resolves via
  `PATH` — which is inherited from Shell Executor's OWN process
  environment (`sandbox.py`'s `_safe_env()`), not hardcoded. Running
  Shell Executor from an activated venv (as every service's own README
  already instructs) resolves this correctly; running it via an
  unactivated interpreter's absolute path does not, even if `ezdxf` is
  correctly listed in `requirements.txt` and installed into that same
  venv. Caught during this phase's own test setup, not a defect in any
  shipped code.
- **Phase 25: a real, reproducible reliability regression, found by
  actually running the candidate upgrade model through the real
  pipeline, not just prompting it once.** `qwen2.5-coder:7b` was pulled
  and evaluated as a `default_local_model` upgrade candidate
  (`docs/aios-forward-plan-phases-25-31.md`'s own Phase 25 scope).
  Single-shot, prompt-only comparison favored it clearly — cleaner code,
  faster (12.9s vs 15.8s), no stray commentary. Run through the real
  `python_agent` pipeline (full rendered prompt, real retry loop) it
  failed **twice, reproducibly**, exhausting all 6 retries both times —
  `schema_invalid_output: not valid JSON`, two different real parse
  errors across the two runs. `qwen3.5:4b` succeeded on the first
  iteration both times it was tried on the identical task. Decision:
  `default_local_model` stays `qwen3.5:4b`; the coder model remains
  pulled and available, evaluated, not adopted. Full detail in
  `docs/aios-architecture-and-phases.md` Phase 25, Section 2.
- **Phase 26: two real, previously latent bugs in `services/assembly/`'s
  prompt-template versioning, found only because this phase modified an
  already-active agent template for the first time in this project's
  history.** `research_agent`'s `template.md`, active since Phase 18,
  had never been changed in place before Phase 26 added
  `research.invoke_mcp_tool`. First: `ensure_template_registered()`
  (every `register.py` since Phase 5) only ever checked template
  *status* ("already active" → skip), never *content* — a changed
  `template.md` would silently never take effect once a template was
  already active. Fixed with a body-diff check, requiring assembly's
  `GET /prompt/templates` to expose `body` (not there before, no caller
  had needed it). Second, more serious: `PromptTemplate.version` is a
  free-text `String` column, and both `register_template()`'s
  `next_version` calculation and `get_active_template()`'s "which
  version is live" query ordered by it lexicographically, where `"9" >
  "10"` — once any agent's template crossed version 9, `next_version`
  would keep recomputing `"10"` forever, and `get_active_template()`
  could serve a stale version-9 body for a live render instead of the
  real, newer version 10. This project's own iterative fixing of
  `research_agent`'s template during this phase pushed it past version 9
  for the first time, exposing a bug latent since Phase 4. Fixed by
  ordering on `created_at` instead of `version` in both places. Full
  detail in `docs/aios-architecture-and-phases.md` Phase 26, Section 3.
- **Phase 27: a stale config value (Phase 23's own known finding) turned
  out to be silently breaking a SECOND, more consequential mechanism —
  the classification-ceiling gate — not just model resolution.**
  `services/platform-spine/platform_spine/config_manager/files/reasoning_engine.yaml`'s
  `default_local_model`/`fallback_local_model` had held `qwen-coder`/
  `deepseek-coder` since Phase 2 — never actually pulled here.
  `resolve_model()` (Phase 23) worked around this with a live
  availability check; `assembly`'s `ceiling_for_model()` (Phase 4/11)
  never did — it only recognizes those two config keys as "local," so
  the model actually used everywhere in this environment (`qwen3.5:4b`)
  was silently downgraded from a `confidential` to a `public`
  classification ceiling. Invisible until Phase 27's own structural
  security bar tried to use it for real: a benign, `internal`-classified
  chat request against the REAL local model was refused live, for the
  wrong reason. Root-caused at the source this time — the config file
  itself is now `default_local_model: qwen3.5:4b`,
  `fallback_local_model: qwen2.5-coder:7b` — not just routed around
  again. Full detail in `docs/aios-architecture-and-phases.md` Phase 27,
  Section 3.

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
- **Every Phase 17 numeric/layout result is structurally, not just
  promptedly, real** — confirmed live: `calc.apply_formula`'s result
  comes from `eval_formula.py`'s actual restricted-AST evaluation of a
  real registered formula (verified with the exact expected computed
  value, `420 * 1.05 = 441.0`, present in the model's next-turn prompt);
  `cutlist.run_optimizer`'s result comes from `cutlist_solver.py`'s
  actual first-fit-decreasing packing of a known input case (verified
  against `services/execution/tests/test_calc_scripts.py`'s identical
  scenario); `autocad.explain_drawing`'s result comes from `dxf_parse.py`'s
  actual `ezdxf` parse of a real generated DXF file (verified with the
  real text content and real computed geometric extents, not the DXF
  header's own potentially-stale `$EXTMIN`/`$EXTMAX` fields).
- **`eval_formula.py`'s restricted evaluator is a real security
  boundary, not a convention**: confirmed live with an actual injection
  attempt (`__import__('os').system(...)`) structurally rejected — the
  AST walker has no code path that reaches a function call at all,
  regardless of what expression string is handed to it.
- **The one genuinely new gap-fill this batch needed**
  (`GET /erp-knowledge/formula/by-name/{name}`) is real, not a stub —
  confirmed live end to end: registering a real formula through the
  existing approval-gated path, then resolving it by name through the
  new endpoint, gets back the exact real `formula_ref` just registered.
- **Phase 18's `security.audit_query` is a genuine tool call, not a
  self-report**: confirmed live — two real audit events were written the
  same way any other service already writes into governance's audit
  trail (a known `correlation_id`, `POST /audit/log`), and both real
  action names are confirmed present in the model's next-turn prompt,
  not paraphrased or guessed at. The `correlation_id` filter it needed
  (governance's real gap-fill) is confirmed live too: querying by that
  exact id returns precisely the two matching events, nothing else.
- **Documentation Agent's `docs.propose_new_doc` proves Phase 16's
  chained-ingest bridge generalizes, not just reuses**: confirmed live
  with a SECOND, independent agent's own approval flow driving
  `reverse_eng_bridge.materialize_propose_documentation()` completely
  unchanged — the resulting document is independently verified via
  Documentation Engine's own `GET /docs/sources` listing, the exact same
  proof Phase 16's own test used.
- **Research Agent's approval requirement is genuinely unconditional,
  not risk-dependent** — confirmed live: `research.propose_external_lookup`
  routes to `awaiting_approval` even when the model self-assesses
  `risk_classification="low"`, the one case in this system where a
  low-risk self-assessment doesn't matter at all, matching the doc's own
  explicit framing that external access is opt-in, never default.
- **Phase 18 shipped with zero real bugs found by live testing** — the
  first phase since Phase 12 where every test passed on its first live
  run against the running stack, worth stating plainly rather than
  padding this section for symmetry with every other phase's write-up.
- **Coding Agent Gateway (Phase 22)'s one new mechanism — a structural
  sandbox-backend safety gate — is confirmed live, both real terminal
  states, not simulated.** `coding_gateway_bridge.py` probes the target
  CLI with a harmless `--version` call through Shell Executor and reads
  back the real `backend` field Shell Executor already returns; when the
  reported backend isn't `docker`, the mutating run is refused before
  any branch/commit/CLI-with-a-real-task ever happens. Live-verified with
  both real providers: `opencode` genuinely isn't installed here
  (`not_configured`), and `claude` (Claude Code, v2.1.215) IS genuinely
  installed but reports `backend: "subprocess"` (no Docker daemon
  anywhere in this environment, unchanged since Phase 6/19), so the gate
  correctly returns `unsafe_backend`. An unplanned second finding from
  that same live run: the real `claude --version` subprocess crashed
  under `SubprocessSandbox`'s 512MB `RLIMIT_AS` cap (exit code -6,
  SIGABRT) — independent confirmation the backend can't safely run this
  CLI, on top of the isolation gap the gate exists to catch. Full detail
  in `docs/aios-architecture-and-phases.md#phase-22-external-coding-agents` Section 7.
- **Model Router (Phase 23) found and fixed a real, previously-invisible
  bug just by checking config against reality.** `default_local_model`/
  `fallback_local_model` are real config keys that have existed since
  Phase 2, but nothing had ever verified the configured default was
  actually pulled in Ollama — confirmed live, it wasn't, and every prior
  phase's live-model test only worked by explicitly overriding
  `target_model`, silently routing around the dead default the whole
  time. `model_router.py`'s `resolve_model()` now checks for real via a
  live `GET /api/tags` and genuinely falls back — live-verified end to
  end: a `target_model=None` execution against a config naming the
  unavailable `qwen-coder` as default resolved to the real,
  actually-pulled `qwen3.5:4b`, confirmed on the persisted
  `ReasoningExecution.target_model` field. `loop.py`'s `generate()` call
  site itself is unchanged — only model-name resolution changed —
  preserving all 46 existing tests that monkeypatch `loop.generate`
  directly. Full detail in `docs/aios-architecture-and-phases.md#phase-23-model-router` Section 6.
- **Phase 26's `research.invoke_mcp_tool` genuinely dispatches through
  extensibility's real, already-tested MCP client — not a new invocation
  mechanism, real wiring of an existing one.** `mcp_bridge.py` resolves a
  model-supplied server *name* to the real, active `server_id` via a live
  lookup against extensibility's `/mcp/servers` (never trusting a
  model-supplied internal id directly, the same discipline
  `execution_bridge.py`'s branch naming already established), then calls
  the real `/mcp/invoke`. Live-tested end to end against a genuine stub
  MCP server (`http.server.HTTPServer` on a real socket, mirroring
  `services/extensibility/tests/conftest.py`'s own pattern): register →
  approve → activate through extensibility's real endpoints, then confirm
  `research_agent`, via a stubbed model response, genuinely calls the
  real tool and the real result folds back into the reasoning loop
  correctly on the next turn. A second test confirms an honest failure
  report — "no active MCP server named X" — when the model names a
  server that was never registered. Full detail in
  `docs/aios-architecture-and-phases.md#phase-26-mcp-surface` Section 2.
- **Phase 27's `/reasoning/raw_generate`, `/reasoning/raw_generate_stream`,
  and `/reasoning/available_models` are real model access, deliberately
  NOT the agentic loop above** — no capability boundary, no template, no
  approval gate, the minimum services/platform-spine's OpenAI-compatible
  shim needs. Built on two new `ollama_adapter.py` functions using
  Ollama's real `/api/chat` (messages-native): `chat()` returns real
  `prompt_eval_count`/`eval_count` token usage from Ollama itself, never
  fabricated; `chat_stream()` is a genuine generator yielding real
  newline-delimited JSON chunks as Ollama actually produces them, live-
  confirmed via `curl -N` to arrive as incremental per-token deltas, not
  a complete response chunked after the fact. Full detail in
  `docs/aios-architecture-and-phases.md#phase-27-openai-compatible-endpoint`
  Section 2.
- **Phase 28's `GET /reasoning/adapters` and `test_adapter_boundary.py`
  are real enforcement, not aspirational documentation.** The registry
  endpoint's `model_providers` entries call each provider's actual
  `is_configured()` live, the same real check `/reasoning/available_models`
  already relies on. The boundary test is a genuine AST scan (Python's
  own `ast` module, not a regex heuristic) of every file under `agents/`
  — verified live to actually flag a violation before being trusted, not
  just asserted to pass. It found one real, previously-unenforced
  inconsistency on its first run: `planner_bridge.py` called `httpx`
  directly instead of going through `agents/clients.py` like every other
  bridge — fixed by moving the call into a new
  `clients.fetch_capability_roster()` function. Full detail in
  `docs/aios-architecture-and-phases.md#phase-28-adapter-contracts`.

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
- **`cutlist_solver.py` is a real, deterministic first-fit-decreasing
  heuristic, honestly labeled as one** (its own output includes
  `"algorithm": "first_fit_decreasing"`) — not a proven-optimal
  bin-packing solver. Swapping in a real ILP/exact solver later is a
  contained change to that one script, per the Phase 17 doc's own
  explicit scope decision.
- **AutoCAD Agent has no native `.dwg` support at all** — a real,
  honestly-named platform constraint (Phase 17 doc, Section 4), not a
  gap worked around. No open-source `.dwg` parser exists and this is a
  Linux environment with no Autodesk tooling; `dxf_parse.py` only ever
  reads real `.dxf` files, assuming a conversion happened upstream.
- **`cutlist.run_optimizer`'s approval requirement is unconditional**,
  not actually detecting "does this specific result feed a downstream
  production-schedule change" the way the master roadmap's own
  conditional phrasing describes — a deliberate Phase 17 scope
  simplification (there's no existing signal this system could check
  that distinction against), documented explicitly rather than silently
  narrowed.
- **Security Agent's `security.audit_query` has no real classification-
  scoped visibility** — the master roadmap's own framing ("audit access
  is itself classification-scoped, no blanket visibility") isn't fully
  realized this phase. `AuditEvent` (Phase 1) has no classification
  field at all today; this agent's real query returns exactly what
  governance's existing, unauthenticated `GET /audit/query` already
  returns to any caller. Named explicitly as a real, unresolved gap
  (Phase 18 doc, Section 0's trade-off), not silently narrowed or faked
  with cosmetic filtering.
- **Research Agent's `propose_external_lookup` never actually looks
  anything up** — by explicit, honest design, not a placeholder for
  something half-built. This system has no external web-access tool
  anywhere in its history (offline-first, `docs/architecture-vision.md`);
  an approved proposal is a real, reviewable document describing what to
  look up and why, for a human to go do manually.
- **`research.invoke_mcp_tool` (Phase 26) is not the open internet
  either** — it only ever reaches an MCP server a human already
  registered, approved, and activated through extensibility's real
  approval flow (Phase 12). A model naming a server that isn't already
  active gets an honest "no active MCP server named X — real active
  servers right now: [...]" back, never a silent failure or a fabricated
  result.
- **Coding Agent Gateway (Phase 22) never actually runs a live external
  coding session in this environment** — not because a binary is
  missing (`claude` is genuinely installed), but because the one
  available sandbox backend (`SubprocessSandbox`, no Docker daemon since
  Phase 6/19) can't isolate a live, credentialed agentic process, and the
  gate refusing that is real, tested code, not a placeholder. The full
  branch → instruction file → invoke → diff → commit → push → open_mr
  path is real and reachable — it only executes when the probe reports
  `backend: "docker"`, which no test run in this environment can ever
  produce. Same honesty tier as `DockerSandbox` itself since Phase 6.
- **Model Router's cloud providers (`OpenAIProvider`, `AnthropicProvider`,
  `GeminiProvider`) are real classes with no real implementation behind
  them.** `is_configured()` genuinely checks for a real API key env var
  (`OPENAI_API_KEY`, etc.) this build never sets; `generate()` on an
  unconfigured provider raises `ProviderNotConfigured` rather than being
  reachable at all. Deliberate, not a placeholder for something
  half-built — this system is offline-first by explicit design, and
  adding a real external call here means real credentials, real cost,
  and real data egress of retrieved context, a decision this phase's own
  doc explicitly declines to make unilaterally (`docs/aios-architecture-and-phases.md#phase-23-model-router`
  Section 0). `resolve_and_generate()` (the dispatcher these providers
  would plug into) is real, tested code, not wired to any call site yet.

## Next

Phase 29 — Tool Adapter Gaps (`docs/aios-forward-plan-phases-25-31.md`):
real browser, live-Odoo, and live-Django adapters built under Phase 28's
now-published contracts — the first genuine test of whether the
`ToolAdapter` shape generalizes to new adapter types rather than just
describing the four that already existed. Real cloud provider support
(a second, genuinely configured `ModelProvider` in `model_router.py`)
remains a product decision, not an engineering one
(`docs/aios-architecture-and-phases.md#phase-23-model-router` Section 0).
Revisiting `qwen2.5-coder:7b` as the AGENTIC pipeline's default is worth
another look if its structured-output reliability gap turns out to be a
fixable prompting/format-constraint issue rather than an inherent model
limitation — not investigated this phase (Phase 25, Section 2); it's
already the real `fallback_local_model` for Phase 27's raw chat
completions, where that gap doesn't apply. Real per-user auth for MCP
Surface and the OpenAI shim's `ide_client` actor both stay deferred to
Phase 31, per the forward plan's own sequencing.
