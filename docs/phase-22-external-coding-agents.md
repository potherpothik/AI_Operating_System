# Phase 22 — External Coding Agents
### Coding Agent Gateway · OpenCode · Claude Code

---

## Built (real code, real live-verified safety gate — see Section 7)

Everything in Sections 1–6 below is the original design, written before any
code existed. It's carried forward unchanged as the record of what was
planned. **Section 7 is new**: what actually got built, and the one real
finding worth knowing before extending this — a live external-agent session
was deliberately never run in this environment, for a structural reason
grounded in code that already existed (Phase 6's `SubprocessSandbox`), not a
new restriction invented for this phase.

---

## 0. Priority Decision: Why a Governed Gateway for External Coding Agents

**Why it exists:** the Coding Brain needs strong code-editing agents without
abandoning governance. OpenCode (open-source coding agent) and Claude Code
are mature CLI agents. The AI Operating System should drive them as
**untrusted tools** inside the existing execution sandbox — not hand them
root access to the ERP or the git remotes.

**Alternatives considered**
- *Replace Reasoning Engine with OpenCode/Claude Code as the primary loop*
  — rejected. That would abandon the shared 6-field schema, Planner,
  Capability Registry, and governance contract that every other agent uses.
- *Shell out to CLIs with no sandbox / no approval* — rejected. Violates
  Phase 1 non-negotiables and Phase 6 branch-protection rules.
- *Reimplement coding agents from scratch only* — slower; ignores capable
  open tools we can wrap. Phase 10 agents stay for scoped Django/DevOps
  work; the gateway is for heavier multi-file coding sessions.
- *Adopt ElizaOS agent-orchestrator as-is* — rejected. Borrow the "spawn
  child agent + inject completion memory" idea
  ([`elizaos-borrowed-ideas.md`](elizaos-borrowed-ideas.md)); keep our
  Python kernel.

**Trade-offs:** CLI surface areas change; the gateway must pin versions and
treat stdout/stderr as untrusted. Offset by writing only to proposal
branches and requiring human approval before merge.

**Security implications:** external agents see repo content inside the
sandbox. They must never receive long-lived secrets, never push to
protected branches, never merge. Output is a proposal diff, same as
`odoo.propose_change` / local coding agents.

**Performance implications:** coding sessions can run minutes; Gateway
must stream progress via Task Manager status, enforce timeouts, and not
block the Planner event loop.

**Future scalability:** same gateway shape can wrap additional CLIs
(Aider, Continue CLI, etc.) behind a `provider: opencode | claude_code |
…` field without new services.

**Estimated complexity:** Medium–High. Mostly wiring and policy; no new
inference stack. Depends on Phase 6 execution sandbox and Phase 1
approval paths already existing.

---

## 1. Coding Agent Gateway

**Responsibilities**
- Accept a governed coding task (`repo_ref`, `branch_base`, `instruction`,
  `provider`, `correlation_id`)
- Materialize a task-scoped instruction file so OpenCode / Claude Code
  inherit this repo's rules (`CLAUDE.md`, `.cursor/rules/`, and a
  generated `AGENTS.md` slice for OpenCode)
- Invoke the chosen CLI inside `services/execution` sandbox with command
  allow-list + resource limits
- Capture the resulting git diff on a proposal branch (server-computed
  branch name; agent never chooses protected targets)
- Return a proposal payload for Human Approval; merge only via existing
  Git Manager rules (never merges itself, no force-push)

**Inputs**
- `{actor, provider: opencode|claude_code, instruction, repo_path_or_ref,
  base_branch?, classification, correlation_id, approval_id?}`

**Outputs**
- `{status: proposed|failed|denied|awaiting_approval, proposal_branch,
  diff_summary, log_ref, risk_classification}`

**APIs** (design target — lives under agents or a thin gateway module,
not a new microservice unless wiring forces it)

| Endpoint / action | Purpose |
|---|---|
| `coding_gateway.run` (capability action) | Start a sandboxed coding session |
| `POST /coding-gateway/runs` (optional HTTP) | Same, if exposed beyond Reasoning Engine |
| `GET /coding-gateway/runs/{id}` | Poll status / logs |
| `coding_gateway.cancel` | Abort a timed-out or user-cancelled run |

**Failure handling:** fail closed. Sandbox unavailable → deny. CLI
non-zero exit → `failed` with logs, no merge. Unreachable Security Layer →
halt. Timeout → kill process group, mark failed, leave dirty worktree
quarantined under sandbox root.

**Logging:** authorize decision, CLI start/end, exit code, diff hash, and
approval id → Audit Logger with `correlation_id`.

**Security:**
- Treat CLI stdout/stderr/files as untrusted content (same
  `<untrusted_context>` posture as retrieved docs).
- No network egress from sandbox beyond what execution policy already
  allows (default: none, or allow-listed package mirrors only under
  approval).
- Secrets only via `secrets.resolve` if a run truly needs them; default
  is none.
- Classification ceiling: `confidential` for source; external model
  backends inside Claude Code remain subject to "never send source
  externally without approval."

**Future extension points:** additional providers; streaming UI; reuse
World/Room session IDs from the ElizaOS-borrowed session model when that
lands.

---

## 2. Provider adapters (OpenCode · Claude Code)

**Responsibilities**
- Know how to invoke each CLI (`opencode …`, `claude …` headless flags)
- Write the task-scoped instruction file into the sandbox worktree
- Normalize exit codes and artifact locations into Gateway's proposal shape

**OpenCode:** prefer `AGENTS.md` (and any OpenCode-native config). Gateway
generates a task-scoped `AGENTS.md` that imports/summarizes governance
constraints and the specific task instruction.

**Claude Code:** already reads root `CLAUDE.md` and can import
`.cursor/rules/*.mdc`. Gateway may append a short task file (e.g.
`.claude/task-<correlation_id>.md`) referenced from the prompt, without
mutating committed `CLAUDE.md`.

**Inputs / Outputs:** same as Gateway; adapters are internal modules.

**Failure handling:** missing binary → `not_configured` (honest), never
fake success. Version skew → pin documented versions in Honesty notes.

---

## 3. How they interact

```
Planner / human task
    → POST /security/authorize  (coding_gateway.run)
    → decision allow | deny | require_approval
         require_approval → POST /approval/request → wait
    → Coding Agent Gateway
         → write task-scoped instructions into sandbox worktree
         → Shell Executor: run OpenCode or Claude Code CLI
              (command allow-list, timeout, cwd = sandbox clone)
         → Git Manager: commit on proposal branch only
         → return diff summary + proposal_branch
    → POST /audit/log
    → Human Approval on merge (existing Git Manager rules)
         approved → merge via Git Manager (never by the CLI)
         rejected/expired → branch left / cleaned per policy
```

---

## 4. Minimal data model

```
coding_run
  id, correlation_id, provider, actor_id
  status: pending|running|proposed|failed|cancelled|denied
  repo_ref, base_branch, proposal_branch
  instruction_hash, diff_hash
  approval_id?, started_at, finished_at, log_ref
```

Capability declaration (design):

```yaml
capability: coding_agent_gateway
brain: coding
allowed_actions:
  - coding_gateway.run
  - coding_gateway.cancel
  - coding_gateway.status
forbidden_actions:
  - git.merge
  - git.force_push
  - "*"
requires_approval:
  - coding_gateway.run   # at least when classification >= confidential
                         # or when provider may call external models
classification_ceiling: confidential
known_limitation: >
  Designed only in Phase 22; CLIs must be installed in the sandbox image;
  SubprocessSandbox vs DockerSandbox honesty notes apply from Phase 6.
```

---

## 5. Folder structure (design target)

Agents stay config over the shared Reasoning Engine; Gateway logic may
live as a module under agents or execution — pick at implementation time
based on whether the CLI invoke is closer to Reasoning Engine tool calls
or Shell Executor. Suggested:

```
services/agents/agents/coding_agent_gateway/
├── capability.yaml
└── template.md

services/execution/execution/coding_gateway/   # optional module
├── adapters/
│   ├── opencode.py
│   └── claude_code.py
├── instruction_files.py
└── run.py
```

Policy additions under `services/governance/.../policies/` for
`coding_gateway.*` actions and CLI allow-list entries under execution
config.

---

## 6. Explicitly out of scope

- Implementing the Gateway code in this documentation round
- Phase 23 Model Router (typed ModelType + priority registry over Ollama)
  — sibling gap; sketched in
  [`architecture-vision.md`](architecture-vision.md) and
  [`elizaos-borrowed-ideas.md`](elizaos-borrowed-ideas.md) §5
- Replacing Phase 10 Django/DevOps/Docker/Testing agents
- Letting external agents merge, force-push, or talk to production DBs
- Bundling OpenCode or Claude Code binaries in this repo
- Adopting ElizaOS as a runtime

---

## 7. What Actually Got Built

**Real code, not a stub:** `services/agents/agents/coding_agent_gateway/`
(capability.yaml, template.md, register.py — config over the shared
Reasoning Engine, no new FastAPI service, matching every Phase 14–18 agent),
`services/agents/agents/reasoning_engine/coding_gateway_bridge.py` (the
materialization logic), a new `coding_agent_gateway.yaml` allowlist under
Shell Executor, and a new `coding_agent_gateway` role in governance's
`default.yaml` (`coding_gateway.propose_run` unconditionally
`require_approval`, matching Section 4's capability declaration design
exactly). `loop.py` dispatches to the bridge after approval via a new
`CODING_GATEWAY_PROPOSE_ACTIONS` set, the same `resume()` pattern every
other propose_* action already uses.

**The one genuinely new mechanism, live-verified, not asserted:** before
any git branch/commit/CLI invocation happens, `coding_gateway_bridge.py`
runs a harmless `<binary> --version` probe through Shell Executor and reads
back the `backend` field Shell Executor already returns on every execution
(`execution_out()`, Phase 6). If that backend isn't `docker`, the function
refuses the mutating run outright — `status: "unsafe_backend"` — rather
than proceeding. This is not a new restriction invented for this phase; it's
Phase 6's own, already-documented finding (`SubprocessSandbox`: "NOT real
filesystem or network isolation") now enforced at the one call site where it
actually matters. Every earlier agent's shell commands were deterministic
scripts or git operations with no live external credentials to leak; an
external coding agent given a real task would run with this environment's
real credentials and unrestricted network access under that backend —
exactly the "untrusted tool" Section 0 says must stay confined.

**Confirmed live, both real terminal states, in this environment:**
- `opencode` genuinely isn't installed (`shutil.which` finds nothing) — the
  real probe returns `status: "not_configured"`.
- `claude` (Claude Code) IS genuinely installed (version 2.1.215) — the real
  probe succeeds as a real process, but reports `backend: "subprocess"` (no
  Docker daemon anywhere in this environment, the same constraint named
  since Phase 6/19), so the gate returns `status: "unsafe_backend"` before
  any branch, instruction file, or CLI invocation with a real task ever
  happens. A second, unplanned finding from the same live test: the real
  `claude --version` subprocess actually crashed under
  `SubprocessSandbox`'s 512MB `RLIMIT_AS` cap (exit code -6, SIGABRT) — a
  second, independent reason this backend can't safely run this CLI, on top
  of the isolation gap the gate is actually checking for.

**What was deliberately never done, and why it's not a stub:** a full,
live, autonomous coding session through this gateway (the actual
`-p "<instruction>"` / `opencode run` path). Not because of a missing
binary — `claude` is right there — but because `SubprocessSandbox`
genuinely cannot contain it safely (no `--network none`, no real filesystem
confinement, this environment's real credentials reachable), and this
environment has never had a Docker daemon since Phase 6. Running it anyway
would mean this system materializing an unconfined, live, credentialed
agent process rather than the sandboxed one every design section above
describes — the gate exists precisely to make that refusal automatic and
structural rather than something a human has to remember to check by hand.
The full run-and-commit code path (branch → instruction file → invoke →
diff → commit → push → open_mr) is real and reachable — it's simply never
reached in this environment, same honesty tier as `DockerSandbox` itself
since Phase 6.

**Tests:** `services/agents/tests/test_phase22_agent.py` — capability
boundaries, live governance policy check, the `not_configured` and
`unsafe_backend` terminal states (both against real, live services, not
mocked), an unknown-provider refusal before any shell call, and a live-model
smoke test (skipped if Ollama unreachable).

---

## Next

Phase 23 — a full Model Router design (typed `ModelType` + priority-ordered
handlers over Ollama, sketched in `architecture-vision.md` §3) when
multi-model routing outgrows the current config-override approach. Phase 24
(Control UI) is designed and waiting when operator-facing UI becomes the
priority.
