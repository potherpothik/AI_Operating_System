# Phase 2 — Platform Spine
### Configuration Manager · Gateway · Task Manager

---

## 0. Priority Decision: Why This Phase Is Second

**Why it exists here:** with governance in place (Phase 1), the system needs a way to actually receive and track work before any agent exists. Config Manager, Gateway, and Task Manager form the "spine" — no intelligence yet, no Ollama, but they establish how work enters the system, how it's tracked, and how the system is configured. Every request through the Gateway calls `Security Layer.authorize()` from the first line of code, not as a retrofit.

**Alternatives considered**
- *Jump to Context Builder / Memory Manager* — rejected as premature. There's no task flow to feed them yet, and designing them without a real task lifecycle risks building against assumptions that don't hold once real tasks exist.
- *Build the first agent immediately as a bare script calling Ollama directly* — rejected. This is exactly the "another chatbot" anti-pattern the mandate rejects outright; it proves nothing about the orchestration layer.
- *Config Manager alone first, defer Gateway/Task Manager* — rejected. Config Manager has no real consumer to validate against in isolation; building the trio together means each is the other's first integration test.

**Trade-offs:** still nothing "intelligent" running after two phases. Offset by this being the *last* no-AI phase — Phase 3 onward builds toward a working agent on top of a substrate that's already stable and secured, instead of debugging plumbing and prompting at the same time.

**Security implications:** the Gateway is the system's outer perimeter — its input validation and authentication are the first line of defense. Task Manager persists potentially sensitive business task content, so it inherits encryption-at-rest and classification rules from Phase 1.

**Performance implications:** this phase fixes the request/response and queueing overhead the system carries forever. Worth getting persistence and correlation-ID tracing right now instead of retrofitting observability later.

**Future scalability:** Task Manager's state model (explicit states, persisted, correlation-ID-tagged) is designed to support a later move to distributed workers without a schema rewrite, even though only a single-node in-process queue is built now.

**Estimated complexity:** Medium-low. Mostly CRUD plus a state machine plus layered config loading. The only real design care is around failure handling — persist before ack, fail-closed on invalid config. No ML dependency yet.

---

## 1. Configuration Manager

*(built first within this phase — Gateway and Task Manager both depend on it at startup)*

**Responsibilities**
- Single source of truth for runtime config: service endpoints, model routing, timeouts, feature flags
- Layered resolution with clear precedence: defaults → environment file → environment variables → runtime override
- Holds the versioned policy-file path/loader that Phase 1's Security Layer reads from
- Hot-reload for non-security config; security-tagged config changes route through the same `Security Layer.authorize()` → `Human Approval Layer` path as any other risky action
- Never stores secret values directly — only references, resolved at runtime via Security Layer's `/security/secrets/resolve`

**Inputs:** config files (YAML), environment variables, runtime override requests (RBAC-gated)

**Outputs:** resolved, typed config object per service; config-change events → Audit Logger

**APIs**

| Endpoint | Purpose |
|---|---|
| `GET /config/{service}` | Resolved config for a service |
| `POST /config/reload` | Hot-reload non-security keys |
| `POST /config/override` | Runtime override — security-tagged keys require Security Layer + Approval |
| `GET /config/schema/{service}` | Introspect expected schema |

**Failure handling:** fail closed on invalid config — refuse to start rather than start partially configured. A bad hot-reload keeps serving last-known-good config and raises an alert instead of applying broken config live.

**Logging:** reads aren't logged (too hot a path); every change (override, reload diff) is logged to Audit Logger with actor and diff.

**Security:** config files are git-tracked, so config-as-code inherits the same branch protection as application code. Secrets are never literal values in config — only references.

**Future extension points:** pluggable config backend (local YAML + env now; a private, still-offline config service like self-hosted etcd/Consul later); per-tenant config if multiple business units need isolation.

---

## 2. Gateway

**Responsibilities**
- Single entry point for all external requests — human users via UI/CLI, external systems via API
- AuthN (validate session/token); delegates AuthZ entirely to `Security Layer.authorize()`
- Rate limiting, request schema validation before anything reaches downstream modules
- Routes validated requests to Task Manager
- Assigns the correlation ID that threads a request through Audit Logger, Task Manager, and every module after it

**Inputs:** HTTP request (session token, payload)

**Outputs:** routed request with `correlation_id`; sync ack or async task handle; rejected/rate-limited response

**APIs**

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/tasks` | Submit a new task — primary entry point |
| `GET /api/v1/tasks/{id}` | Poll task status |
| `GET /api/v1/tasks/{id}/stream` | SSE/websocket stream of task progress |
| `GET /healthz` | Liveness — feeds the future Health Monitor |

**Failure handling:** auth failures return 401/403 with no detail that could leak *why* (avoids oracle attacks). Downstream unavailability returns 503 with retry-after rather than silently queueing into a black hole; circuit breaker on calls to Task Manager.

**Logging:** access-log level — correlation_id, actor, endpoint, outcome — for every request. Distinct from Security Layer's authorization-decision log, joinable on `correlation_id`.

**Security:** TLS termination, request size limits, strict schema enforcement at the boundary. No raw request body ever reaches a tool without passing Security Layer classification first.

**Future extension points:** pluggable auth backends (local store now; SSO/LDAP later, since an enterprise ERP typically already has directory services); websocket gateway for real-time agent status; gRPC surface if needed.

---

## 3. Task Manager

**Responsibilities**
- Owns task lifecycle end to end: `queued → planning → in_progress → review → done/failed`
- Persists task state — survives restarts, which matters once agent work can run long
- Exposes a dequeue interface for the Planner (Phase 4+) to pull work from
- Tracks parent/child subtask relationships once a task gets decomposed
- Emits status events for the Gateway's streaming endpoint and the future Metrics Dashboard

**Inputs:** task submission `{title, description, requested_by, priority, context_refs}`; status updates from downstream modules

**Outputs:** task record with current state; queue of pending tasks; status-change events

**APIs** *(internal — Gateway is the only external-facing caller)*
- `enqueue(task)`, `dequeue(agent_capability)`, `update_status(task_id, status, detail)`, `get_task(task_id)`, `list_tasks(filter)`

**Failure handling:** task state is persisted before the submission is acknowledged — no task acked then lost on crash. Stuck-task detection flags anything past SLA in `in_progress` instead of letting it silently disappear. Retries are explicit and bounded, never open-ended.

**Logging:** every state transition logged — `task_id, from_status, to_status, actor, timestamp` — operational logging, joinable to the security audit trail via `correlation_id`.

**Security:** task payloads can carry business-sensitive ERP content, so task records at rest inherit Phase 1's encryption-at-rest requirement. Before a task is handed to an agent capability, Task Manager confirms with Security Layer that the capability is authorized for that task's data classification.

**Future extension points:** priority/SLA-based scheduling; cancellation and rollback; distributed task manager once single-node throughput becomes a real bottleneck — deliberately not built now, but the state model won't need a rewrite to get there.

---

## 4. How the Three Interact

```
Human / external caller
        │
        ▼
     Gateway  ── validates token (authN)
        │
        ├── Security Layer.authorize() ──► Audit Logger (logs decision)     [Phase 1]
        │
        ▼ (if allowed)
  Task Manager.enqueue(task)
        │
        ├── persist task record (status=queued)
        ├── Audit Logger (logs creation, correlation_id)                    [Phase 1]
        └── status events ──► Gateway streaming endpoint

  Configuration Manager
        │
        ├── serves resolved config to Gateway + Task Manager at startup
        └── config changes ──► Security Layer.authorize() ──► Human Approval Layer
                                (only for security-tagged keys)              [Phase 1]
```

---

## 5. Minimal Data Model for This Phase

```sql
-- tasks
task (
  id, correlation_id, title, description, requested_by,
  priority, status, parent_task_id, context_refs,
  created_at, updated_at
)
task_event (id, task_id, from_status, to_status, actor, detail, ts)

-- config (file-based; overrides tracked here)
config_override (id, service, key, value_ref, set_by, set_at, requires_approval)
```

---

## 6. Folder Structure for This Phase

```
platform/
├── gateway/
│   ├── api.py            # /api/v1/tasks* endpoints
│   ├── auth.py            # session/token validation
│   ├── middleware.py       # rate limiting, correlation_id, schema validation
│   └── streaming.py         # SSE/websocket status stream
├── task_manager/
│   ├── api.py            # internal enqueue/dequeue/update interface
│   ├── state_machine.py    # status transitions + validation
│   ├── store.py            # persistence
│   └── models.py
└── config_manager/
    ├── api.py
    ├── loader.py            # layered resolution: defaults → file → env → override
    ├── schema/              # per-service pydantic schemas
    └── files/               # versioned YAML config (git-tracked)
```

---

## 7. Explicitly Out of Scope for This Phase

No Planner (task decomposition), no agents, no Ollama calls, no Memory/Vector Search, no Git/Shell/DB tool execution. Tasks are accepted, validated, authorized, persisted, and queued — nothing "thinks" about them yet.

---

## Next

Phase 3: Memory Manager + Vector Search — the knowledge substrate that Context Builder (Phase 4) and every agent (Phase 5+) will draw from, so the first real agent isn't grounded in nothing.
