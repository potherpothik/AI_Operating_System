# Phase 1 — Governance Layer
### Security Layer · Audit Logger · Human Approval Layer

---

## 0. Priority Decision: Why Governance Is Built First

**Why it exists (as Phase 1, ahead of Gateway/Task Manager/agents):**
Every other module either calls into this layer or has no safety envelope without it. The mandate's own non-negotiables — *"source code is highly confidential," "never send source code to external APIs unless explicitly approved," "security by default"* — are only true if enforcement exists before anything can act. An agent, tool executor, or gateway built before governance exists will either ship with no real enforcement, or with a stub that hardens into production behavior by inertia.

**Alternatives considered**
- *Skeleton-first* (Gateway + Task Manager, security stubbed as always-allow) — rejected. Stubs become permanent, and everything built against a fake authorizer needs rework once the real one lands.
- *Agent-first* (ship one working agent — e.g. Odoo Agent — to prove value fast) — reasonable as the *next* phase, wrong as the *first*. Its actions would be unlogged and unreviewed by construction.
- *Memory / Vector Search first* — not on the critical security path; better built in parallel or after.

**Trade-offs:** delays the first visible demo. Offset by keeping this phase deliberately narrow — three modules, zero ML/inference dependency — so it ships fast and nothing downstream needs to retrofit security later.

**Security implications:** this phase *is* the security implication — it's the enforcement point every later phase assumes already exists.

**Performance implications:** adds one synchronous authorization hop before every tool call. Mitigated with in-process policy evaluation for the common case (no network round-trip); only the approval-required path pays for a remote call.

**Future scalability:** starts with an embedded rule evaluator rather than a full policy engine, with an explicit swap-in point for Open Policy Agent (OPA) once policy complexity grows. Avoids overbuilding now without blocking scale later.

**Estimated complexity:** Medium. No Ollama/model dependency in this phase — fully buildable and testable in isolation. Realistic for one phase with 1–2 senior engineers: a policy data model, a decision API, an append-only log store, and a request/approve workflow with a CLI or minimal UI.

---

## 1. Security Layer

**Responsibilities**
- Single Policy Decision Point (PDP) for every tool call, agent action, and model invocation
- RBAC across three actor types: human users, agents, tools
- Secret resolution — issues short-lived credentials, never hands out raw long-lived secrets
- Prompt-injection defense: taint-tracks content retrieved from documents/DB/web as "untrusted," strips/flags embedded instructions before they reach a tool-executing agent
- Content classification — does this payload contain source code / secrets / PII? Feeds the "never send source code externally without approval" rule directly
- Model isolation policy — which model tier (local-only vs. any external call) may see which classification of content
- Defines sandbox and branch-protection policy consumed by Shell Executor / Git Manager

**Inputs**
- Action request: `{actor, actor_type, action, resource, payload_classification, context}`
- Identity/session token
- Current policy set (from Configuration Manager)

**Outputs**
- Decision: `allow | deny | require_approval`, with reason code and obligations (e.g. "redact before proceeding")
- Redacted/sanitized payload when partially allowed
- Policy-violation event → Audit Logger

**APIs**

| Endpoint | Purpose |
|---|---|
| `POST /security/authorize` | Core PDP call: `{actor, action, resource, context}` → `{decision, reason, obligations}` |
| `POST /security/classify` | Classify content: source code / secret / PII / public |
| `GET /security/policy/{role}` | Introspect effective policy for a role |
| `POST /security/secrets/resolve` | Exchange a secret reference for a short-lived credential |

**Failure handling:** fail closed, always. Any exception, timeout, or unreachable policy store → deny. If the Security Layer itself is unreachable, the orchestration layer halts rather than degrading to "fail open" — non-negotiable given the confidentiality requirement.

**Logging:** every decision is logged synchronously to the Audit Logger before the caller receives it. An unlogged authorization is equivalent to no authorization.

**Security:** the Security Layer's own admin surface uses stronger auth than the rest of the system (mTLS, local-bind only). Its policy files are version-controlled and gated by the same branch-protection rules it enforces on everyone else.

**Future extension points:** swap the embedded rule evaluator for OPA; pluggable secrets backend (start with SOPS+age or self-hosted Vault — cloud KMS can't be assumed available); pluggable classifier (regex/heuristic now, local ML classifier later).

---

## 2. Audit Logger

**Responsibilities:** append-only, tamper-evident record of every security-relevant event — auth decisions, tool executions, approvals, config changes, and any model call together with the data classification sent to it.

**Inputs:** `{timestamp, actor, action, resource, decision, context_hash, correlation_id}`

**Outputs:** persisted entry; query results for review/forensics; anomaly alerts (later)

**APIs**

| Endpoint | Purpose |
|---|---|
| `POST /audit/log` | Write event (internal-only: Security Layer, Tool/Execution Layer) |
| `GET /audit/query` | Search by actor/time/action, RBAC-gated |
| `GET /audit/export` | Compliance / disaster-recovery export |

**Failure handling:** writes for high-risk actions (shell exec, git push, DB migration) are synchronous and blocking — if the write fails, the action does not proceed. Low-risk read-path events may buffer locally and retry async.

**Logging:** the logger writes its own failures to a separate local fallback file, so the audit trail's own health is itself auditable.

**Security:** storage is append-only at the data layer (DB trigger denying UPDATE/DELETE, or a hash-chained log in the style of git commits) so a compromised agent can't cover its tracks. Encrypted at rest.

**Future extension points:** SIEM export (self-hosted ELK/Wazuh); Merkle-proof tamper evidence; automated retention policy per data-classification tier.

---

## 3. Human Approval Layer

**Responsibilities:** intercepts anything the Security Layer flags `require_approval` — protected-branch pushes, shell commands matching a risk pattern, any content leaving the local-model boundary, schema-altering migrations, production deploys — and holds it pending until a human decides.

**Inputs:** `{action, risk_classification, requested_by, diff_or_preview, expiry}`

**Outputs:** `approved | rejected | expired`, notification back to the requester

**APIs**

| Endpoint | Purpose |
|---|---|
| `POST /approval/request` | Create a pending approval (called via Security Layer's obligation) |
| `GET /approval/pending` | List open requests for an approver role |
| `POST /approval/{id}/decide` | Approve/reject, with optional comment |
| Notification hook | Pluggable — Slack/email where available; local CLI/dashboard polling always works offline |

**Failure handling:** requests expire to **rejected**, never to auto-approved. If the approval service itself is down, actions simply stay pending.

**Logging:** every request and decision → Audit Logger.

**Security:** high-risk approvals require the approver to re-authenticate at decision time, not just hold a logged-in session — limits the blast radius of a hijacked session approving something destructive.

**Future extension points:** quorum/multi-approver for the highest risk tier; delegated approval; graduated autonomy — well-understood, low-risk, repeatable actions can move from "always ask" to "policy-approved" once enough clean history exists.

---

## 4. How the Three Interact

```
Agent/Tool requests an action
        │
        ▼
Security Layer .authorize()  ──────────────►  Audit Logger (logs the decision)
        │
        ├── allow ──────────────────────────► action proceeds
        │
        ├── deny ───────────────────────────► action blocked, agent gets reason
        │
        └── require_approval
                │
                ▼
        Human Approval Layer .request()  ───► Audit Logger (logs the request)
                │
        (human reviews via CLI / dashboard / notification)
                │
                ▼
        approved ──► action proceeds ──► Audit Logger (logs execution)
        rejected/expired ──► action blocked ──► Audit Logger (logs outcome)
```

---

## 5. Minimal Data Model for This Phase

```sql
-- policy: version-controlled, loaded by Configuration Manager, cached in-process
role (id, name, description)
role_permission (role_id, action_pattern, resource_pattern, effect)  -- effect: allow/deny/require_approval

-- audit: append-only
audit_event (
  id, ts, actor_id, actor_type, action, resource,
  decision, reason, context_hash, correlation_id, prev_hash  -- chains to prior row's hash
)

-- approvals
approval_request (
  id, action, risk_tier, requested_by, payload_ref,
  status, created_at, expires_at, decided_by, decided_at, comment
)
```

`prev_hash` gives a cheap hash-chain (each row hashes the previous row) without a full Merkle tree yet — that's the noted future extension.

---

## 6. Folder Structure for This Phase

```
governance/
├── security/
│   ├── api.py            # /security/* endpoints
│   ├── policy_engine.py  # embedded rule evaluator (OPA-swappable later)
│   ├── classifier.py     # content classification
│   ├── secrets.py        # secrets backend interface
│   └── policies/         # versioned policy files (YAML)
├── audit/
│   ├── api.py
│   ├── store.py          # append-only store + hash chain
│   └── fallback.log
├── approval/
│   ├── api.py
│   ├── notifier.py       # pluggable notification backends
│   └── store.py
└── shared/
    ├── models.py          # pydantic models for the three APIs above
    └── config.py          # reads from Configuration Manager
```

---

## 7. Explicitly Out of Scope for This Phase

No agents, no Ollama/model calls, no Gateway, no Git/Shell/DB tool execution. Zero inference dependency by design — this phase is fully buildable and testable before a single line of agent code exists.

---

## Next

Phase 2: Gateway + Task Manager + Configuration Manager — built to call `Security Layer.authorize()` on the very first request, not bolted on afterward.
