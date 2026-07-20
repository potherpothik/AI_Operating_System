# Phase 13 — Metrics Dashboard · Health Monitor

---

## 0. Priority Decision: Why This Phase Now

**Why it exists here:** both modules are read-only aggregation over data every prior phase already produces — no new instrumentation needed, just a place to look at it. Deferred until now because there was nothing meaningful to monitor before Phase 5's first agent existed, and little worth dashboarding before Phase 10/14's agent roster gave the system real usage variety.

**Alternatives considered**
- *Build this right after Phase 2, once Task Manager existed* — rejected. A dashboard over one module (queued/in-progress task counts) would have been trivial and not representative of what a real operations view needs once six-plus services are actually producing activity.
- *Push write-capable remediation into this phase (auto-restart a stuck module, auto-expire a stuck task)* — rejected. The doc's own design intent is explicit: read-only by design, surfacing problems for a human rather than auto-remediating, consistent with the human-in-the-loop philosophy every other phase already follows. A dashboard that could mutate state would need the full governance treatment everything else gets.
- *Add a real-time push/websocket layer this phase* — rejected as premature; polling is sufficient today and named as a future extension point once there's a concrete reason to need push-based latency.

**Trade-offs:** neither module produces new data — everything they show is only as fresh, and only as complete, as the underlying service's own records. A handful of small, genuinely necessary listing endpoints had to be added to six earlier services (governance, agents, knowledge, knowledge_pipelines, execution, database) since none of them previously exposed a *list* of their own log/execution records, only single-record lookups or write paths. This is the same "extend by unblocking existing gaps" pattern every prior phase has followed, not new surface area invented for its own sake — see Section 2.

**Security implications:** read-only means failures here never risk system state — worst case is a stale or unavailable view, never a bad write. Access is still classification-scoped: a viewer without clearance for confidential-tier activity sees aggregate counts, not task content at that tier. Access itself is logged lightly, since even aggregated metrics can be sensitive (an approval-queue count hints at pending risky actions).

**Performance implications:** this phase's own load is bounded — a handful of HTTP GETs per poll against services that were already handling far more traffic than this. The genuinely new load is on the six services gaining listing endpoints: each is a straightforward indexed query, not a new hot path.

**Future scalability:** real-time streaming (websocket) instead of polling; anomaly detection on metrics feeding back into Security Layer as a signal — e.g. an unusual spike in approval requests from one capability.

**Estimated complexity:** Medium. No new inference stack, no new governance mechanism — mostly wiring a new service to poll six others, plus six small, mechanically similar listing endpoints.

---

## 1. Gap-fill: listing endpoints six existing services were missing

Every metric named below needs to enumerate *multiple* records of something a service already stores — but every existing service before this phase only exposed single-record lookups (`GET /approval/{id}`, `GET /reasoning/{execution_id}/trace`) or write paths, never a list. Each addition below is a small, real, tested GET endpoint on the *owning* service — Health Monitor and Metrics Dashboard do their own aggregation over the raw rows, they do not gain write access anywhere and the owning services gain no new write surface either.

| Service | New endpoint | Backs |
|---|---|---|
| `governance` | `GET /approval` (optional `status` filter) | Approval queue depth, time-to-decision |
| `agents` | `GET /reasoning/executions` (optional `status`/`agent_capability` filter) | Reasoning iterations per task, stuck-past-`max_iterations` detection |
| `knowledge` | `GET /vector/stats` extended with `by_classification` | Classification distribution of served content |
| `knowledge_pipelines` | `GET /erp-knowledge/snapshots` | Stale ERP knowledge detection (Phase 9's `stale` status, across every `target_db`, not just one you already know to ask about) |
| `execution` | `GET /shell/executions` (optional `capability`/`status` filter) | Tool execution volume by capability |
| `database` | `GET /db/query-log` (optional `capability`/`query_type` filter) | Tool execution volume by capability (data side) |

None of these touch governance's authorize/approval *write* paths — they are plain, unauthenticated-the-same-way-every-other-GET-in-this-system-is reads. "Task Manager's SLA flag," named in the original design language of this phase, does not exist as a stored field on Phase 2's `Task` model — no phase ever added one. Health Monitor computes staleness itself from `Task.updated_at`/`created_at` against a configurable threshold instead of assuming a flag that was never built; this is called out explicitly rather than silently invented.

---

## 2. Health Monitor

**Responsibilities:** liveness/readiness checks across every module built since Phase 2's Gateway `/healthz`, aggregated into one system view. Surfaces degraded states already *defined* in earlier phases but with nowhere to report to until now: Security Layer unreachable (a system-halt condition per Phase 1), stuck tasks (computed from Task Manager timestamps — see Section 1's honesty note), stale ERP knowledge (Phase 9's `stale` flag, now visible across every target without knowing which one in advance), reasoning executions stuck past `max_iterations` (Phase 5). Deliberately does not auto-remediate — surfaces problems for a human, consistent with the system's human-in-the-loop philosophy throughout; auto-restarting a stuck module without review could mask a real problem.

**Inputs:** a static, env-var-configured registry of every known service's base URL (same `*_URL` convention every service already uses to call its own peers); no request body beyond that for `GET /health/system`.

**Outputs:** per-service status (`up | down | degraded`), plus a `gaps` list of the structurally-defined degraded states above, each with enough detail (task id, snapshot target_db, reasoning execution id) for a human to act on without a second lookup.

**APIs:** `GET /health/system` · `GET /health/{module}` · `POST /health/alert-config`

**Failure handling:** a single unreachable service is reported as `down` for that entry, never allowed to fail the whole aggregate response — one dead peer must not blind the view of every other service. Security Layer itself being unreachable is reported as a distinguished top-level `governance_reachable: false` flag (not just one more `down` entry), since every other service's own authorization depends on it — this is the one entry Health Monitor treats as more than routine.

**Logging:** each poll's aggregate result is audit-logged lightly (which services were down, which gaps were found) — not per-service-per-poll, which would flood the audit log for a routine health check.

**Security:** `GET /health/system` and `GET /health/{module}` return status/counts only, never task or execution *content* — no classification ceiling parameter needed since nothing above `internal`-shaped metadata (a task id, a status string) is ever in the response body. `POST /health/alert-config` reuses Human Approval Layer's existing `payload_ref`-shaped request mechanism as its "offline-capable notification hook" — configuring an alert destination is itself logged, not a new notification channel invented for this phase (see Section 5 for the honest scope of what this actually does today).

**Future extension points:** real alerting integration (email/Slack webhook) once a real deployment has a destination to send to; auto-remediation suggestions (not auto-remediation itself) surfaced alongside a detected gap.

---

## 3. Metrics Dashboard

**Responsibilities:** aggregates operational metrics already generated as a byproduct of every phase's own logging — task throughput/latency (Task Manager), reasoning iterations per task (Reasoning Engine), approval queue depth and time-to-decision (Human Approval Layer), tool execution volume by capability (Shell Executor/Database Connector), classification distribution of served content (Vector Search/Context Builder). Read-only by design — a dashboard that could mutate system state would need the full governance treatment everything else gets, so it deliberately doesn't get write access to anything.

**Inputs:** same static service registry Health Monitor uses; an optional `since` timestamp on `GET /metrics/{category}` to scope the aggregation window.

**Outputs:** `GET /metrics/overview` returns one number per category (today's snapshot); `GET /metrics/{category}` returns the detailed breakdown backing that number; `GET /metrics/export` returns the full aggregate payload as JSON, for feeding into an external dashboard tool this phase does not build.

**APIs:** `GET /metrics/overview` · `GET /metrics/{category}` · `GET /metrics/export`

**Failure handling:** the same per-source isolation as Health Monitor — a category whose source service is unreachable is reported with a `partial: true` flag and the categories that *did* succeed still return real numbers, never a single unreachable dependency blanking the whole response.

**Logging:** access is logged lightly (who queried which category, when), since even aggregate counts can be sensitive — an approval-queue depth spike hints at pending risky activity even without seeing what it is.

**Security:** classification-scoped where a category's underlying rows carry a classification (today: the `classification_distribution` category, sourced from Vector Search's own `by_classification` breakdown). Every other category is pure counts/durations with no content, so no ceiling parameter applies to them.

**Future extension points:** real-time streaming (websocket) instead of polling; anomaly detection on metrics feeding back into Security Layer as a signal.

---

## 4. How It Fits In

```
GET /health/system
        │
        ▼
Health Monitor
        ├── polls every known service's own /healthz  (up/down/degraded)
        ├── queries governance's new GET /approval (pending count, age)
        ├── queries platform-spine's GET /api/v1/tasks (stuck-by-timestamp heuristic)
        ├── queries agents' new GET /reasoning/executions (stuck past max_iterations)
        └── queries knowledge_pipelines' new GET /erp-knowledge/snapshots (status=stale)

GET /metrics/overview
        │
        ▼
Metrics Dashboard
        ├── platform-spine: GET /api/v1/tasks               → throughput/latency
        ├── agents:         GET /reasoning/executions (new)  → iterations per task
        ├── governance:     GET /approval (new)               → queue depth, time-to-decision
        ├── execution:      GET /shell/executions (new)        → tool volume by capability
        ├── database:       GET /db/query-log (new)             → tool volume by capability
        └── knowledge:      GET /vector/stats (extended)          → classification distribution
```

Neither module ever calls a POST/mutating endpoint on any peer service — every arrow above is a GET.

---

## 5. Honest Scope of `POST /health/alert-config`

This phase does not build a real notification channel (no email/Slack/webhook integration exists anywhere in this codebase). `POST /health/alert-config` persists a configured threshold + a `payload_ref`-shaped destination description, the same shape Human Approval Layer already accepts — calling it "reuses Human Approval Layer's offline-capable notification hook" means literally that: the hook is *offline-capable* because nothing here requires a live notification integration to exist, the same way Human Approval Layer itself doesn't require one to function (a human polls `GET /approval/pending` today; this phase doesn't change that). A real alert integration is a named future extension point, not silently implied to already work.

---

## 6. Minimal Data Model

```sql
-- Health Monitor's own state
alert_config (
  id, metric_or_gap, threshold, destination_ref, created_by, created_at
)

health_poll_log (
  id, polled_at, services_down JSON, gaps_found JSON
)

-- Metrics Dashboard has no persistent store of its own — every response
-- is computed live from the six services above, per request. Nothing to
-- keep consistent, nothing that can go stale on its own.
```

Everything else this phase reads already has a table: `ApprovalRequest` (governance), `Task`/`TaskEvent` (platform-spine), `ReasoningExecution` (agents), `Document` (knowledge), `ErpSchemaSnapshot` (knowledge_pipelines), `SandboxExecution` (execution), `DbQueryLog` (database).

---

## 7. Folder Structure

```
observability/
├── health_monitor/
│   ├── api.py
│   ├── registry.py       # the static *_URL service list
│   ├── checks.py          # the four structurally-defined gap checks
│   ├── models.py
│   └── store.py
└── metrics_dashboard/
    ├── api.py
    ├── aggregator.py       # per-category query + aggregation logic
    └── registry.py         # shared with health_monitor's service list
```

---

## 8. Explicitly Out of Scope

Real alerting integration (email/Slack/webhook) — `alert-config` persists the intent, nothing sends anything yet. Real-time streaming/websocket updates — polling only. Auto-remediation of any detected gap — this phase surfaces problems for a human, never acts on them. A generic multi-service log aggregator (e.g. centralized structured logging) — this phase aggregates specific, already-defined *metrics*, not raw logs.

---

## Next

Phase 15: the operations agents (Manufacturing, Sales, Project Management) — the natural continuation of Phase 14's business-agent batch, now with a real operations dashboard to watch their activity through once built.
