# Phase 2 — Platform Spine (working implementation)

Configuration Manager, Gateway, and Task Manager — real, tested code. Gateway
calls Phase 1's Security Layer over actual HTTP, the way they'll run as
separate services in production (Phase 19), not as a same-process shortcut.

## Run it

```bash
pip install -r requirements.txt

# Phase 1 must be running first — Gateway calls it for every request.
# In a separate terminal, from the Phase 1 project:
#   uvicorn main:app --port 8000

export SECURITY_LAYER_URL="http://localhost:8000"   # default if unset
uvicorn main:app --port 8002
```

**One-time setup:** Phase 1's `governance/security/policies/default.yaml` needs
`task.create`, `task.read`, and `task.update_status` rules for whichever roles
should be able to submit tasks — `odoo_agent`'s policy file already ships with
these added. If you're adding a new role, give it the same three rules.

## Test it

```bash
# Unit tests only (Config Manager, Task Manager state machine) — no dependencies:
pytest tests/ -q

# Full suite including Gateway integration tests, which need Phase 1 reachable:
PHASE1_PATH=/path/to/phase1-governance pytest tests/ -v
```

Without `PHASE1_PATH` set and no Security Layer already running, the 5 tests
that need it skip cleanly rather than failing confusingly — everything else
still runs. With it set, conftest.py starts a real Phase 1 instance for the
test session and tears it down afterward.

23 tests total: layered config resolution and security-tagged override
gating, the task state machine's valid and invalid transitions, enqueue/
dequeue/list behavior, and Gateway's auth, rate limiting, and end-to-end task
creation — the last of which makes a real network call to Phase 1, not a
mock.

**Phase 15 addition:** `GET /api/v1/tasks/{task_id}/events` — the real,
ordered state-transition history behind a task's current snapshot.
`task_manager/store.py`'s `task_events()` has existed since this phase
was first built but was never reachable over HTTP until Project
Management Agent's `task.read` tool call
(`services/agents/agents/reasoning_engine/task_bridge.py`) needed it —
nothing before that needed more than the current-status snapshot
`GET /api/v1/tasks/{task_id}` already provides.

## Verified live, not just under the test harness

Ran both services as real processes against real Postgres and confirmed:

- Task creation succeeds end-to-end, including the cross-service authorize
  call to Phase 1
- Missing/invalid auth → 401; rate limit → 429; invalid state transition →
  400; unknown task → 404
- **Killing Phase 1 mid-flight and immediately retrying returns:**
  `{"detail":"security layer unreachable, failing closed: ..."}` — Gateway
  genuinely fails closed when Security Layer is down, not just in theory.

## Phase 24 gap-fill: conversations + task threading + SSE token auth

Real additions for `services/control-ui`'s BFF and `web/` frontend:
`Conversation` model plus `Task.conversation_id` (nullable — a task with no
conversation still works exactly as before), `POST`/`GET /api/v1/conversations`,
`GET /api/v1/conversations/{id}`, and a `conversation_id` filter on
`GET /api/v1/tasks`. Live-tested, both SQLite and real Postgres.

**No migration framework exists in this project** (`Base.metadata.create_all()`
creates missing tables but never alters existing ones) — extending `task`,
an already-live table in the real `platform` Postgres database from earlier
phases' own testing, needed one explicit, manual, additive statement:
`ALTER TABLE task ADD COLUMN conversation_id VARCHAR;`. Nullable, no data
loss, no default backfill needed. Anyone else running this against their
own already-populated Postgres instance needs the same statement — not
automated, named here so it isn't a surprise.

**`GET /tasks/{id}/stream`'s new `?token=` fallback**
(`platform_spine/gateway/auth.py`'s `resolve_actor_for_stream`): the browser's
real `EventSource` API cannot set an `Authorization` header at all — a
genuine platform limitation, not a workaround for a bug. Scoped to this one
endpoint only; every other route still requires the real header via the
original `resolve_actor`, unchanged.

## Phase 26 addition

`tokens.yaml` gained `dev-mcp-surface-token: mcp_surface` — the fixed,
stub-auth bearer token `services/mcp-surface/` (Phase 26) uses for its
`submit_task` calls into Gateway. Same explicitly-a-placeholder posture
this file has always had (see "What's a stub" below); no new mechanism.

## Postgres

Tested directly against a live Postgres instance, including under a
deliberately non-UTC session timezone (the same class of bug found in
Phase 1 — timestamp columns use `DateTime(timezone=True)` from the start
here, not retrofitted, and `tests/test_task_manager.py::
test_task_timestamps_survive_round_trip_as_the_same_utc_instant` locks
that in). `psycopg2-binary` is in `requirements.txt`.

```bash
export DATABASE_URL="postgresql://user:pass@host:5432/platform"
```

## What's a stub

`platform_spine/gateway/auth.py` maps bearer tokens to actor names via a
local YAML file (`tokens.yaml`) — explicitly a placeholder for real SSO/LDAP
integration, labeled as such in the code. Rate limiting is in-memory and
per-process; fine for a single instance, won't coordinate across multiple
Gateway replicas without a shared store (Redis or similar) — noted as a
future extension, not built here.

## What's next

Task Manager's `dequeue()` is ready for Planner (Phase 8) to call, but
nothing calls it yet — tasks created now just sit in `queued`, exactly as
the design doc scoped this phase. Phase 3 (Memory Manager, Vector Search)
is next, and doesn't depend on Phase 2 at all — it can be built and tested
independently, same as Phase 1 was.
