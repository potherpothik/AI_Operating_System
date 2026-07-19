# Phase 6 — Execution Layer
### Shell Executor · Git Manager

*A note on scope: the mandate lists "sandbox execution" as a security requirement, not a standalone module. It's treated here as Shell Executor's core mechanism rather than a third module — exactly like "branch protection" and "read-only mode" are properties of Git Manager and Shell Executor respectively, not separate services.*

---

## 0. Priority Decision: Why This Phase Is Sixth

**Why it exists here:** with Reasoning Engine and Odoo Agent proving the pipeline (Phase 5), agents can reason and propose but not yet act — `odoo.propose_change` today produces text a human applies by hand. This phase turns "propose" into "safely execute, on a branch, pending human merge." Shell Executor and Git Manager are paired because Git Manager is, mechanically, a policy-aware consumer of Shell Executor — separating them across phases would mean either Git Manager reimplementing sandboxed execution itself, or Shell Executor existing with nothing meaningful to run yet.

**Alternatives considered**
- *Bundle Database Connector into this phase too, since it's also "execution"* — rejected for now. Database writes carry a different, arguably higher blast radius than a commit on a disposable branch (data loss and corruption are harder to reverse), and deserve their own dedicated phase alongside Database Agent rather than being a third item bolted on here.
- *Give every agent its own embedded sandboxed executor* — rejected outright. Same "reinvented and under-secured per agent" failure mode flagged when Context Builder/Prompt Builder were designed as shared infrastructure — one heavily-scrutinized execution chokepoint is far easier to secure and audit than many copies.
- *Let Git Manager call the git CLI directly, bypassing Shell Executor, since "it's just git"* — rejected. Git commands run on real user-influenced input (commit messages, branch names, file paths) and are exactly the command-injection surface Shell Executor's sandboxing and allow-listing exist to contain. No command gets an exception to "only Shell Executor executes."

**Trade-offs:** this is the first phase where the system becomes capable of doing real, if contained, damage — meaningfully higher stakes than anything so far. Offset by defense-in-depth: Security Layer authorization, Shell Executor's sandbox and allow-list, Git Manager's structural branch protection, and Human Approval Layer gating any mutating action — no single one of these is trusted to be sufficient alone.

**Security implications:** this phase makes the mandate's "sandbox execution" and "branch protection" requirements concrete. Alongside Phase 1 and Phase 4, this is one of the three most safety-critical phases in the whole build.

**Performance implications:** container-per-execution has real startup latency (hundreds of ms to a few seconds depending on image caching) — acceptable given agents currently propose changes occasionally rather than executing at high frequency, but worth flagging as a future optimization target.

**Future scalability:** allow-list-per-capability plus the Shell Executor/Git Manager split means giving a future agent execution rights (e.g. DevOps Agent running `docker compose`) is an allow-list entry and a capability declaration, not new sandboxing infrastructure.

**Estimated complexity:** Medium-high. Sandbox isolation correctness is genuinely hard to get right — this phase is where "security by default" is tested most directly — even though it reuses Docker, already in the stack.

---

## 1. Shell Executor

**Responsibilities**
- The *only* module in the system permitted to execute shell commands — everything else that needs to run something, including Git Manager, calls through it
- Sandboxed execution: container-per-execution by default (Docker is already in the stack) — only the working directory mounted, no network unless explicitly granted, CPU/memory/time limits enforced, non-root inside the container
- Command allow-listing per agent capability, default-deny — an agent gets a declared set of permitted command patterns, not "run anything not blocked"
- Every request goes through `Security Layer.authorize()` first — Shell Executor enforces policy, it doesn't set it
- Read-only vs. mutating mode flag: read-only executions (`git diff`, `pytest --collect-only`) may skip Human Approval Layer per Security Layer's obligations; mutating ones typically require it
- Captures stdout/stderr/exit code and streams results back to Reasoning Engine's loop

**Inputs:** `{command, args, working_dir, capability, requesting_agent, task_id, mode: read_only|mutating}`

**Outputs:** `{exit_code, stdout, stderr, duration, sandbox_id}`

**APIs**

| Endpoint | Purpose |
|---|---|
| `POST /shell/execute` | Core execution call |
| `GET /shell/{sandbox_id}/status` | Poll/stream a long-running command |
| `POST /shell/{sandbox_id}/kill` | Abort a running execution |

**Failure handling:** fail closed — if Security Layer is unreachable, nothing executes, mirroring Phase 1's own halt rule. Sandbox-creation failure surfaces as an explicit error and never falls back to running unsandboxed. Timeouts trigger a hard kill and `failed: timeout`, never a process left running unattended.

**Logging:** every execution — full command, args, working directory, requesting agent, exit code — logged to Audit Logger, including read-only ones, at lighter detail than mutating commands.

**Security:** the highest-blast-radius module built so far — the literal boundary between the system reasoning about things and changing something on a real machine. Container-per-execution, no network by default, read-only mounts unless a command is explicitly mutating, non-root execution, allow-list rather than block-list.

**Future extension points:** resource-limit tuning per command type; a scoped, still-isolated persistent workspace for multi-step workflows if per-call container startup becomes a bottleneck; GPU-aware sandboxing for future build/test steps.

---

## 2. Git Manager

**Responsibilities**
- All version-control operations — branch, commit, diff, push — implemented as policy-aware calls into Shell Executor's sandboxed `git`, never a separate git implementation
- Branch protection: agent-originated changes always land on a new, agent-named branch; protected branches (main/production) can never be pushed to directly
- Code ownership: a CODEOWNERS-style mapping routes each proposed change's approval request to the human who actually owns that path, not a generic queue
- Commit provenance: every agent-originated commit carries a structured trailer (`task_id`, `agent_capability`, `context_id`, `reasoning_execution_id`), so any commit traces back to the exact reasoning trace and context that produced it
- Opens the merge/pull request and attaches the agent's proposal text and `risk_classification` (from Phase 5's structured output) as the description
- Never merges — merging stays an exclusively human action via the git hosting UI/CLI; Git Manager's job ends at "MR opened, pending"

**Inputs:** `{action: branch|commit|diff|push|open_mr, repo, files_changed, message, task_id, agent_capability, context_id, reasoning_execution_id}`

**Outputs:** `{result, branch_name, commit_sha, mr_url_or_ref}`

**APIs**

| Endpoint | Purpose |
|---|---|
| `POST /git/branch` | Create an agent-scoped branch |
| `POST /git/commit` | Commit with structured provenance trailer |
| `POST /git/diff` | Read-only diff — no approval needed |
| `POST /git/push` | Push to the agent's own branch only |
| `POST /git/open_mr` | Open a merge/pull request with proposal + risk_classification attached |

**Failure handling:** any attempt to target a protected branch is rejected inside Git Manager itself, before it ever reaches Shell Executor — defense in depth, not reliance on Security Layer or server-side hooks alone. Push conflicts/rejections surface clearly; force-push is never permitted from an agent context, so failures are never silently retried with `--force`.

**Logging:** every git action logged with its full provenance trailer to Audit Logger — combined with Shell Executor's own execution log, this gives two independent, cross-checkable records of the same event.

**Security:** branch-protection and force-push denial are enforced structurally in Git Manager's own code, not only as an external policy check — the push target is computed by Git Manager itself, never taken from agent input. Even if Git Manager were somehow bypassed, `git push --force origin main` still wouldn't appear in any agent's Shell Executor allow-list. Agent-originated commits are signed (GPG or equivalent) so they're cryptographically distinguishable from human commits in history.

**Future extension points:** automatic changelog drafting from commit provenance trailers; forge-specific adapters (GitHub, GitLab, self-hosted Gitea) behind one interface — the git hosting choice shouldn't leak into agent-facing code, in keeping with vendor independence.

---

## 3. How the Two Interact — Odoo Agent's Proposal, End to End

```
Reasoning Engine (Phase 5): agent output = odoo.propose_change, risk_classification=medium
        │
        ▼
Human Approval Layer.request(...)                                          [Phase 1]
        │  (human approves)
        ▼
Reasoning Engine.resume(...)
        │
        ▼
Git Manager.branch("odoo-agent/task-{id}")
        ├── Shell Executor.execute("git checkout -b ...", mode=mutating)
        │        └── Security Layer.authorize() ──► Audit Logger              [Phase 1]
        │        └── sandboxed container, allow-listed command
        ▼
Git Manager.commit(files, message, provenance_trailer)
        ├── Shell Executor.execute("git commit ...", mode=mutating)
        ▼
Git Manager.push(agent's own branch only)
        ├── Shell Executor.execute("git push ...", mode=mutating)
        │        (branch-protection check already happened in Git Manager)
        ▼
Git Manager.open_mr(proposal text, risk_classification)
        └── MR opened, pending human merge — Git Manager stops here
```

---

## 4. Minimal Data Model for This Phase

```sql
sandbox_execution (
  id, task_id, requesting_capability, command, args, working_dir,
  mode, exit_code, stdout_ref, stderr_ref, duration_ms, created_at
)

git_action (
  id, task_id, reasoning_execution_id, context_id, action,
  repo, branch_name, commit_sha, mr_ref, provenance_trailer, created_at
)

capability_command_allowlist (
  agent_capability, command_pattern, mode   -- read_only | mutating
)
```

---

## 5. Folder Structure for This Phase

```
execution/
├── shell_executor/
│   ├── api.py
│   ├── sandbox.py                # container-per-execution via Docker
│   ├── allowlist.py               # per-capability command patterns
│   └── store.py                    # sandbox_execution persistence
└── git_manager/
    ├── api.py
    ├── branch_policy.py             # protected-branch + force-push denial
    ├── provenance.py                 # commit trailer construction
    ├── codeowners.py                  # path → approver routing
    └── forge_adapter/                  # github.py / gitlab.py / gitea.py, one interface
```

---

## 6. Explicitly Out of Scope for This Phase

No Database Connector — deferred to its own phase given its distinct blast radius. No MCP Client or Plugin System — future phases for extending tool reach beyond shell/git. Git Manager never merges; that stays a human action outside this system's automation boundary by design, not a missing feature.

---

## Next

Phase 7: Database Connector + Database Agent — paired the same way Shell Executor led into Git Manager: connector infrastructure alongside the first agent that actually exercises it, given the deferred blast-radius concern flagged above.
