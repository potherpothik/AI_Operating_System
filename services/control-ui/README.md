# Phase 24 — Control UI BFF (working implementation)

Real, tested code. The aggregation and governed-write proxy fronting `web/`,
the first operator-facing UI in this repo. Holds no orchestration logic of
its own — every real decision (authorize, audit, task lifecycle, approval
lifecycle) still happens in the same services every other phase already
built; this service exists so the browser doesn't have to fan out to five
different origins and re-implement the authorize → audit → forward pattern
in JavaScript.

## Run it

```bash
pip install -r requirements.txt
export SECURITY_LAYER_URL=http://localhost:8000
export PLATFORM_URL=http://localhost:8002
export OBSERVABILITY_URL=http://localhost:8013
uvicorn main:app --port 8024
```

## Test it

```bash
export PHASE1_PATH=/path/to/services/governance
export PHASE2_PATH=/path/to/services/platform-spine
pytest tests/ -v
```

10 tests, all passing on the first live run: bootstrap reachability
reporting, conversation create/list/get proxied through platform-spine,
timeline merging real tasks with their real event history, the approvals
inbox listing real pending requests, and — the one action this service
actually governs — `POST /ui/approvals/{id}/decide` confirmed to really
authorize, really forward to governance, and really change that approval's
status (checked independently against governance's own `GET /approval/{id}`
afterward, not just trusting the BFF's own response).

## Try it live

```bash
curl -H "Authorization: Bearer dev-admin-token" http://localhost:8024/ui/bootstrap
# → {"actor":"human_admin","services":{"governance":true,...},"capability_views":[]}

curl -X POST -H "Authorization: Bearer dev-admin-token" -H "Content-Type: application/json" \
  -d '{"title":"Sale order questions"}' http://localhost:8024/ui/conversations
```

## What's real vs. what's a stub

**Real:** every endpoint in `control_ui/api.py` calls a real peer service —
conversations and timeline through platform-spine, approvals through
governance, reachability checks through live HTTP calls, not assumed.
`POST /ui/approvals/{id}/decide` is a genuine governed proxy: it calls
`POST /security/authorize` for `approval.decide` first, audit-logs the
decision either way, and only forwards to governance's own
`POST /approval/{id}/decide` on `allow` — confirmed live end to end.

**Stubbed / deliberately out of scope this phase:**
- **Auth is a stub YAML token file** (`control_ui/tokens.yaml`), same
  convention as Gateway's own `platform_spine/gateway/tokens.yaml` — not
  real SSO/LDAP. The two files are independent (matching this project's
  established pattern of per-service authorization data — allowlists, PII
  registries — rather than one shared store), but share the same token
  strings for the dev-admin path so a browser session's one token works
  against both this BFF and Gateway directly.
- **Capability views (`GET /ui/views`) are honestly empty.** The Phase 24
  design doc's own gap-fill table (§1) names a `GET /plugins/views` manifest
  listing as a prerequisite — `services/extensibility/` has no such
  endpoint or view-manifest convention today. Returning `{"views": []}` is
  a real, valid answer to "what capability views exist," not a placeholder
  for a broken feature.
- **Approvals inbox is NOT enriched with task/conversation links**, despite
  the design doc's own §3 API table naming that as the intent. Real reason:
  `ApprovalRequest` (`services/governance/governance/models.py`) has no
  `correlation_id` or `task_id` field — there is nothing real to join
  against. A further gap-fill on governance's own schema would be needed to
  close this; not done this session, named here rather than faked with an
  empty or invented link.
- **No `ui_user_preferences`/`ui_widget_state` tables** — the Phase 24 doc's
  §11 sketches these for per-user widget layout persistence, but nothing in
  this session's v1 frontend actually reads or writes per-user preferences,
  so this service holds no database of its own at all. Adding unused tables
  "for later" would violate this project's own no-speculative-abstraction
  discipline; add them when a real feature needs them.
- **No SSE multiplex at the BFF** (`GET /ui/conversations/{id}/stream` from
  the design doc §3 is not implemented) — the frontend uses Gateway's own
  existing per-task SSE stream directly instead (see `web/README.md`), a
  real, working substitute for v1, not a missing feature silently dropped.

## Next

Real Postgres-backed persistence for `ui_user_preferences` if/when a real
feature needs it. A `GET /plugins/views` manifest convention on
`services/extensibility/` to make the capability-views catalog genuinely
non-empty. A `correlation_id`/`task_id` field on governance's
`ApprovalRequest` to make the approvals inbox's task/conversation
enrichment real instead of a named gap.
