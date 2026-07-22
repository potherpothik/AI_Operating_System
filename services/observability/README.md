# Phase 13 — Health Monitor & Metrics Dashboard (working implementation)

Real, tested code. Both modules are read-only aggregation over data every
prior phase already produces — no new instrumentation, just a place to
look at it. Health Monitor surfaces degraded states earlier phases already
*defined* but had nowhere to report to (Security Layer unreachable, stuck
tasks, stale ERP knowledge, reasoning executions that burned every
iteration without resolving). Metrics Dashboard aggregates task
throughput/latency, reasoning iterations, approval queue depth and
time-to-decision, tool execution volume by capability, and classification
distribution. Neither module has a write path to anything — a dashboard
that could mutate system state would need the full governance treatment
everything else gets.

Six earlier services needed one small, real listing endpoint each — see
`docs/aios-architecture-and-phases.md#phase-13-metrics-dashboard-health-monitor` Section 1. None of them gained a new
write surface; each is a plain GET over data that service already stored.

## Run it

```bash
pip install -r requirements.txt
# every peer service below must already be running for a genuinely
# useful response; unreachable ones just show up as "down" or "partial"
export GOVERNANCE_URL=http://localhost:8000
export PLATFORM_URL=http://localhost:8002
export KNOWLEDGE_URL=http://localhost:8003
export ASSEMBLY_URL=http://localhost:8004
export AGENTS_URL=http://localhost:8005
export EXECUTION_URL=http://localhost:8006
export DATABASE_CONNECTOR_URL=http://localhost:8007
export PLANNING_URL=http://localhost:8008
export KNOWLEDGE_PIPELINES_URL=http://localhost:8009
export EXTENSIBILITY_URL=http://localhost:8010
# Phase 2's Gateway requires a bearer token on GET /api/v1/tasks — there
# is no distinct read-only-viewer role in tokens.yaml, only the same stub
# token→role file every phase since 2 documents as standing in for real
# SSO/LDAP. Defaults to the admin token; override if your deployment adds
# a dedicated viewer token.
export GATEWAY_TOKEN=dev-admin-token
uvicorn main:app --port 8013
```

## Test it

```bash
pytest tests/ -v
```

19 tests, all passing against the real live stack — not mocked, except
for two deliberately-stubbed unit tests (an unreachable-source `partial`
case, and the stuck-reasoning-executions filter tested against a
synthetic response shape — see "What's real" below for why). One live
Ollama smoke test (`test_reasoning_iterations_reflects_a_real_completed_execution`)
skips cleanly if Ollama isn't reachable, same convention as every other
phase's own live-model test.

## Real bugs found by live testing, not the test suite

- **`clients.get_tasks()` had no Authorization header at all.** Phase
  2's Gateway requires a bearer token on `GET /api/v1/tasks`
  (`resolve_actor`); the first live call returned 401, silently
  swallowed by the broad `except Exception: return []` every client
  function here uses to keep one dead dependency from blinding the rest
  of an aggregate response — so the failure looked like "no tasks exist
  yet," not "this call was rejected." Fixed by sending a real bearer
  token (`GATEWAY_TOKEN`, same pattern `agents/clients.py` already
  established for Task Manager writes).
- **Naive-vs-aware datetime comparison** in both `checks.py`'s and
  `aggregator.py`'s `_parse_ts()`. A peer service running on SQLite (the
  zero-setup default every service falls back to without an explicit
  `DATABASE_URL`) drops timezone info on round-trip — `DateTime(timezone=True)`
  only really means `TIMESTAMPTZ` against Postgres, the same class of
  gap Phase 1's own honesty notes already document. Comparing a naive
  timestamp parsed back from JSON against `datetime.now(timezone.utc)`
  raises `TypeError: can't compare offset-naive and offset-aware datetimes`
  — caught by actually running the stuck-task check against a real task
  created moments earlier, not by any unit test in isolation. Fixed by
  normalizing a naive parse result to UTC (every `_now()` helper in this
  codebase already produces UTC regardless of what SQLite hands back).
- **A test using an invented capability name** (`metrics_test_capability`)
  for the tool-execution-volume test failed closed at governance's own
  `authorize()` — a useful reminder that this system's "extend by
  unblocking existing gaps" discipline applies to test fixtures too, not
  just services: a capability needs a real governance policy role before
  it can do anything, even in a test.

## What's real

- **Health Monitor's aggregate poll is genuinely resilient to a dead
  peer** — confirmed live: `extensibility` and `planning` weren't
  started for one test run, and `GET /health/system` still returned a
  complete response with those two correctly marked `down`, never a
  500 or a partial crash.
- **`governance_reachable` is a real, distinguished top-level flag**,
  not just one more row in the services list — matches
  `governance-first.mdc`'s framing that every other service's own
  authorization depends on this one being real.
- **Every structural gap check queries real, live data**: `check_stuck_tasks`
  against a real task pushed through Task Manager's actual state
  machine (confirmed both that a genuinely fresh task is NOT flagged,
  and that the same task IS flagged once the threshold is lowered to 0);
  `check_stale_erp_knowledge` against ERP Knowledge Engine's real
  `current`-status snapshot after an actual sync. The one honestly-mocked
  check is `check_stuck_reasoning_executions`'s own unit test — see
  "What's a stub" below for why forcing a genuine iteration-exhaustion
  live wasn't the right trade for this phase.
- **Metrics Dashboard's numbers are computed from real activity, not
  canned**: `task_throughput_latency` reflects a task actually pushed
  through `queued → in_progress → review → done` with a real measured
  latency; `approval_queue`'s time-to-decision is computed from a real
  governance approval that was actually decided; `tool_execution_volume`
  reflects a real `db.read` that actually ran against `demo_erp`;
  `classification_distribution` reflects a real document actually
  ingested at `confidential`; `reasoning_iterations` reflects a real,
  live-model execution through the actual `agents` service, not a
  stubbed response (this module can't import agents' Python code to
  monkeypatch its model call — separate service, separate process — so
  this one category's test is a genuine live-Ollama smoke test).
- **A category whose source is unreachable reports `partial: true` with
  honest zeros**, confirmed live by monkeypatching only the client
  boundary this module owns (`clients.get_tasks`) — never a single
  unreachable dependency blanking the whole `/metrics/overview` response.

## What's a stub or simplified

- **`POST /health/alert-config` persists the intent only — no real
  notification channel exists anywhere in this codebase** (no
  email/Slack/webhook integration). This is not silently claimed to
  "send an alert"; it stores a threshold + destination description a
  human (or a future real integration) reads back, the same
  "offline-capable" posture Human Approval Layer already has (a human
  polls `GET /approval/pending` today; this doesn't change that). See
  `docs/aios-architecture-and-phases.md#phase-13-metrics-dashboard-health-monitor` Section 5 for the full reasoning.
- **`check_stuck_reasoning_executions`'s own test mocks
  `clients.get_reasoning_executions`** rather than forcing a genuine
  Reasoning Engine iteration-exhaustion through the live `agents`
  service. Reasoning Engine's loop is synchronous — `execute()` runs its
  iterations and returns — so reliably engineering a real stuck
  execution from outside that service (no shared process, no way to
  monkeypatch its model call across a service boundary) isn't a
  trustworthy trigger to build a test around. The filtering logic itself
  is tested for real against a synthetic response matching the real,
  independently-verified contract of `GET /reasoning/executions`
  (`services/agents/tests/test_reasoning_engine.py`).
- **No real-time streaming (websocket)** — polling only, a named future
  extension point in the design doc.
- **No anomaly detection** — metrics are reported as-is; a future
  extension point, not attempted this phase.
- **`GATEWAY_TOKEN` defaults to the admin stub token**, not a dedicated
  read-only viewer identity — Phase 2's auth is a stub token→role file
  with no distinct viewer role defined, the same honest gap already
  documented for Planner's own classification-ceiling limitation in
  Phase 8. Health Monitor and Metrics Dashboard have no write path
  regardless of which token resolves them, so this doesn't grant any
  capability beyond read access to already-read-only endpoints.

## Next

Phase 15: the operations agents (Manufacturing, Sales, Project
Management) — the natural continuation of Phase 14's business-agent
batch, now with a real dashboard to watch their activity through.
