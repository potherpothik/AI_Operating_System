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

42 tests total (23 as of Phase 2; Phase 24's conversation/SSE gap-fill,
Phase 27's OpenAI shim, and Phase 31's real OIDC auth wiring added the
rest): layered config resolution and
security-tagged override gating, the task state machine's valid and
invalid transitions, enqueue/dequeue/list behavior, Gateway's auth, rate
limiting, and end-to-end task creation — the last of which makes a real
network call to Phase 1, not a mock — plus `/v1/chat/completions` and
`/v1/models` (see the Phase 27 section below).

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

## Phase 27 addition — OpenAI-Compatible Endpoint

`gateway/openai_shim.py` adds `POST /v1/chat/completions` (+ real SSE
streaming) and `GET /v1/models` — the "GPU-day switch": any IDE that
already speaks the OpenAI chat-completions shape can select AIOS as its
model provider. `tokens.yaml` gained `dev-ide-client-token: ide_client`.
A thin translator, not a second model layer: real generation happens in
`services/agents/` (new `/reasoning/raw_generate`/`raw_generate_stream`),
real classification happens in `services/governance/` (Phase 1's
existing `/security/classify`), real ceiling-checking happens in
`services/assembly/` (Phase 4/11's existing `ceiling_for_model()`). Every
request is classified and ceiling-checked against its target model
BEFORE any model call — confirmed live: a request naming an unrecognized
model (`ceiling="public"`) with ordinary business content
(`classification="internal"`) gets a real 403, and the identical request
against the real local model succeeds — both outcomes written to the
real, hash-chained audit trail.

**A real, previously latent bug found and fixed along the way:**
`config_manager/files/reasoning_engine.yaml`'s `default_local_model`/
`fallback_local_model` had held `qwen-coder`/`deepseek-coder` since Phase
2 — literal values never actually pulled in this environment (Phase 23's
own finding, worked around there but never corrected at the source).
This phase found a second, more consequential place trusting that stale
value without checking reality: assembly's `ceiling_for_model()` only
recognizes these two config keys as "local," so the model actually used
everywhere in this environment (`qwen3.5:4b`) was silently getting a
`public` ceiling instead of `confidential` — this phase's own structural
bar caught it live, refusing a benign request against the real local
model for the wrong reason. Corrected at the source:
`default_local_model: qwen3.5:4b`, `fallback_local_model: qwen2.5-coder:7b`.
One pre-existing test (`test_config_manager.py`) updated to match.

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

## Phase 31 addition — real per-user auth (`AUTH_MODE=oidc`)

`platform_spine/gateway/auth.py`'s `tokens.yaml` mapping is no longer
the only option: `AUTH_MODE=oidc` resolves a bearer token as a real
OIDC access token, verified against `services/identity/` (Phase 31's
new self-hosted provider) via governance's own `/security/verify_token`.
`resolve_actor()` returns the token's real per-user `sub` (not a shared
stub name); `resolve_raw_token_if_oidc()` — a new dependency, `None`
under the default `AUTH_MODE=stub` — lets `authorize()` call sites pass
the raw token through so governance can verify it itself and authorize
by the token's real `role` claim rather than trusting `actor` as a
policy role unverified. Confirmed live: `POST /api/v1/tasks` with a real
OIDC token creates a task whose `requested_by` is the real `sub`
(`human-admin-001`), and `openai_shim.py`'s `GET /v1/models` (it shares
this same `auth.py`) works identically under the same real token.
Default stays `AUTH_MODE=stub` — every prior phase's tests and tokens
keep working unchanged.

## What's a stub

Rate limiting is in-memory and per-process; fine for a single instance,
won't coordinate across multiple Gateway replicas without a shared
store (Redis or similar) — noted as a future extension, not built here.
`AUTH_MODE=stub` (the default) still maps bearer tokens to actor names
via a local YAML file (`tokens.yaml`) — real per-user auth exists now
(`AUTH_MODE=oidc`, above), but stub stays the default so nothing built
against it across 30 phases breaks.

## What's next

Task Manager's `dequeue()` is ready for Planner (Phase 8) to call, but
nothing calls it yet — tasks created now just sit in `queued`, exactly as
the design doc scoped this phase. Phase 3 (Memory Manager, Vector Search)
is next, and doesn't depend on Phase 2 at all — it can be built and tested
independently, same as Phase 1 was.
