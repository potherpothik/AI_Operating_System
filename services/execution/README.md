# Phase 6/17 — Shell Executor & Git Manager (working implementation)

Real, tested code. The highest-stakes phase so far — the first time the
system can make a real, if contained, change on disk. Shell Executor is
the *only* module permitted to run a shell command; Git Manager is a
policy-aware consumer of it, never a separate git implementation. Phase
17 added a new kind of artifact under `shell_executor/scripts/`: real,
reviewed, deterministic Python tools (`eval_formula.py`, `cutlist_solver.py`,
`dxf_parse.py`) that Calculation/Cutlist Optimization/AutoCAD Agents
invoke via the exact same sandboxed-subprocess path every other
allowlisted command already uses — never the model's own arithmetic or
layout guess. See `services/agents/README.md`'s Phase 17 section for the
full mechanism and the bridges that call these scripts.

## Run it

```bash
pip install -r requirements.txt
export SECURITY_LAYER_URL=http://localhost:8000   # governance must already be running
export SANDBOX_ROOT=/tmp/ai_os_sandbox              # working_dir confinement boundary
uvicorn main:app --port 8006
```

`agents` (Phase 5) points `EXECUTION_URL` at this service and
`PROPOSAL_REPO_PATH` at a real git working directory inside `SANDBOX_ROOT`
to close the loop described below.

## Test it

```bash
pytest tests/test_branch_policy.py tests/test_provenance.py tests/test_codeowners.py \
       tests/test_allowlist.py tests/test_sandbox.py -q   # no external dependencies

SECURITY_LAYER_URL=http://localhost:8000 pytest tests/ -v   # full suite, governance auto-started if PHASE1_PATH is set
```

72 tests, all passing against real Postgres (genuine `TIMESTAMPTZ`
columns under a non-UTC session) and real git — `test_git_manager.py`
runs branch/commit/diff/push/open_mr against a real, disposable bare
repo created fresh per test run, never the actual project repo.
`test_calc_scripts.py` (Phase 17) tests `shell_executor/scripts/`
directly, as real subprocesses, independent of any live model: a real
computed formula result, a real injection attempt structurally rejected
(never reaching a function call regardless of the input string), a real
known bin-packing case, and real DXF parsing including a real
geometric-extents computation confirmed to differ from (and be more
accurate than) the DXF header's own potentially-stale fields.

## Docker isn't installed in this environment — read this before trusting sandbox isolation

Confirmed directly: no `docker` binary on `PATH` here. `DockerSandbox` is
written to the real `docker run` contract (container-per-execution, no
network by default, read-only mount unless `mode=mutating`, non-root,
`--pids-limit`) but has never actually run in this environment — same
honesty pattern as Phase 3's untested `OllamaEmbedding`. What's actually
been tested here is `SubprocessSandbox`, the automatic fallback:

- **Real**: working-directory confinement to `SANDBOX_ROOT` (any path
  outside it is rejected before a command ever runs), a minimal explicit
  env allowlist (not the parent process's full environment — confirmed:
  an arbitrary env var set on the host does not leak into a sandboxed
  command), a hard timeout with genuine process termination, and CPU/
  memory resource limits via the `resource` module.
- **Not real**: filesystem isolation beyond the working-dir check (a
  command can still read/write outside `working_dir` via an absolute
  path) and network isolation (nothing blocks outbound network from a
  subprocess). The command allowlist (`allowlist.py`, default-deny) is
  the actual defense against this gap — only pre-approved command
  patterns per `agent_capability` ever reach the sandbox at all.

`get_sandbox()` picks `DockerSandbox` automatically the moment `docker`
is on `PATH` — no code change needed, same swap mechanism as the
embedding model in Phase 3.

**Phase 22 made this gap concrete, not just theoretical.** Coding Agent
Gateway's `coding_gateway_bridge.py` probes an external CLI (Claude Code /
OpenCode) with `<binary> --version` before ever handing it a real task, and
reads back this execution's own `backend` field to decide whether to
proceed. Live-confirmed in this environment: `claude` (Claude Code) really
is installed, the probe genuinely runs, and it reports `backend:
"subprocess"` — so Coding Agent Gateway refuses the mutating run outright,
never handing a live, credentialed external agent to a backend that can't
isolate its network or filesystem access. A second, unplanned finding from
that same live probe: the real `claude --version` process crashed under
this backend's 512MB `RLIMIT_AS` cap (exit code -6, SIGABRT) — the resource
limits meant for isolating small deterministic scripts turn out to be too
tight for a real Node/Bun-runtime CLI, an independent reason this backend
isn't the right one for that specific workload. Full detail in
`docs/aios-architecture-and-phases.md#phase-22-external-coding-agents` Section 7 and
`services/agents/README.md`.

## A real bug found by live testing, not the test suite

The first version set `RLIMIT_NPROC(64, 64)` in the subprocess sandbox as
a would-be per-execution process-count limit. Live-testing `git push`
against a real (local, disposable) bare repo failed with `fatal: unable
to fork` — `RLIMIT_NPROC` is scoped **per UID, system-wide**, not per
subprocess tree, so the host's own ambient process count (everything else
this session was already running) silently ate into the budget for a
command that did nothing wrong. Removed from `SubprocessSandbox`, which
now only sets the resource limits it can actually scope correctly
(CPU, memory). `DockerSandbox` uses `--pids-limit`, which *is* correctly
cgroup-scoped per-container — real per-execution process limiting needs
that, not a bare rlimit. Locked in as a permanent regression test
(`test_command_that_forks_a_child_process_is_not_blocked`).

## What's real

- **Phase 17 addition:** three new real, reviewed, deterministic scripts
  under `shell_executor/scripts/` — `eval_formula.py` (a restricted
  `ast`-based arithmetic evaluator, structurally incapable of anything
  beyond named-variable arithmetic, confirmed live with an actual
  injection attempt rejected before it ever reaches a function call),
  `cutlist_solver.py` (a real first-fit-decreasing bin-packing
  heuristic, honestly labeled as one in its own output), and
  `dxf_parse.py` (real `ezdxf`-based DXF parsing, using
  `ezdxf.bbox.extents()` for real geometric bounding-box computation
  rather than trusting a DXF file's own potentially-stale header
  fields). All three are invoked the exact same way any other
  allowlisted command already is — a real sandboxed subprocess, no new
  execution mechanism. `ezdxf` needs to be importable by whichever
  `python3` this service's own process resolves via `PATH` — activate
  this service's venv before running it (same as every other service's
  own README already instructs), or `dxf_parse.py` reports a clean
  `ezdxf not installed` error rather than silently failing.
- **Phase 16 addition:** `POST /git/diff` is genuinely driven by an
  agent for the first time — Code Review Agent's `review.fetch_diff`
  tool call (`services/agents/README.md`'s Phase 16 section). No code
  changed here; the endpoint's existed, read-only and un-approval-gated,
  since Phase 6. A real bug surfaced by that first live caller: a bare
  branch name compares to the working tree, not `main` — fixed on the
  caller's side (`review_bridge.py` builds `main...{branch}`), not here,
  since `/git/diff` correctly runs whatever real `git diff` args it's
  given.
- **Phase 13 addition:** `GET /shell/executions` (optional
  `requesting_capability`/`status` filters) — no listing endpoint
  existed before this, only per-id status. Backs Observability's
  Metrics Dashboard's tool-execution-volume-by-capability category.
- **Default-deny command allowlisting per `agent_capability`**, loaded
  from `shell_executor/allowlists/*.yaml` — an unknown capability or an
  unlisted command pattern is rejected before Shell Executor ever tries
  to run it. Confirmed live: `rm -rf` for `odoo_agent` is denied, not
  merely undeclared.
- **Branch protection is structural, not just policy**: `branch_policy.py`
  computes the push target itself — it is never taken from caller input —
  and rejects `main`/`master`/`production` or any branch outside the
  calling agent's own `{capability}/task-*` namespace *before* the
  request ever reaches Shell Executor. Confirmed live: pushing to `main`
  or another agent's namespace is rejected with the real remote left
  completely untouched (verified by reading the remote's own log
  directly, not trusting the service's response).
- **Commit provenance is a real git trailer**, not metadata bolted on
  separately — confirmed live by reading the actual commit message back
  from the disposable remote (`Task-Id`, `Agent-Capability`, `Context-Id`,
  `Reasoning-Execution-Id` all present).
- **Agent-originated commits use a distinct git identity**
  (`Odoo Agent <agent+odoo_agent@ai-orchestration.local>`), injected as
  explicit `GIT_AUTHOR_*`/`GIT_COMMITTER_*` env vars for the sandboxed
  commit call — confirmed it does *not* silently inherit the host's own
  global git config, which is what would have happened without this fix.
- **The Phase 5 → Phase 6 loop genuinely closes**: an approved
  `odoo.propose_change` (Reasoning Engine's `resume()`, Phase 5) now
  really calls Git Manager — branch, commit (with the model's proposal
  text written as a real file), push, open_mr — against a real
  disposable repo, verified independently by reading the remote's log
  and file contents directly, not just trusting the returned status. See
  `services/agents/agents/reasoning_engine/execution_bridge.py`.
- **Phase 10's `devops_agent`, `docker_agent`, and `testing_agent`
  allowlists reuse this exact mechanism with zero code changes** — new
  YAML files under `allowlists/`, nothing else. `docker_agent.yaml` has
  no mutating command at all (only read-only `docker ps`/`logs`/
  `inspect`/`compose` patterns plus its own scoped git branch for
  `docker.propose_compose_change`) — `docker exec`/`stop`/`rm` are
  structurally absent, not merely policy-denied one layer up, confirmed
  by `test_docker_agent_has_no_mutating_commands_at_all`.
- **Phase 11's `on_commit` trigger is real, not just documented**: a
  successful `/git/commit` fires a best-effort call to Code Analysis
  Engine's `/code-analysis/scan(mode=incremental)`, reusing the SAME
  `files_changed` list the commit request already carried rather than
  computing a separate git diff. Confirmed live: a real commit through
  this service's own `/git/branch` and `/git/commit` produced a real
  call graph and real Vector Search content in `knowledge_pipelines`
  moments later. `CODE_ANALYSIS_URL` unset (the default) makes this a
  genuine no-op — confirmed by NOT monkeypatching HTTP in
  `test_code_analysis_trigger_is_a_real_no_op_when_unconfigured`, so a
  live network attempt with nothing listening would have raised, not
  returned quietly, if the "unconfigured" branch weren't actually taken
  first.

## What's a stub or simplified

- **GPG commit signing** (the doc's "cryptographically distinguishable
  from human commits") isn't implemented — no signing key exists in this
  environment, and generating one wasn't done unilaterally. The distinct
  git author/committer identity above is the honest baseline achievable
  without one; swapping in real signing is a `git commit -S` flag plus a
  configured key, not an architecture change.
- **`GitHubAdapter.open_pr`** is written to GitHub's real REST API
  contract but has never been called against real GitHub — no `gh` CLI
  and no `GITHUB_TOKEN` here, and deliberately not exercised against the
  actual project repo even if a token existed (opening a real PR is a
  publishing action). Reports `not_configured` cleanly rather than
  crashing or faking success — confirmed in every test that reaches it.
- **`odoo.propose_change` commits the model's proposal TEXT as a review
  document** (`proposals/{task_id}.md`), not a computed code diff — Odoo
  Agent's Phase 5 output schema has `answer_or_proposal` as prose, it was
  never asked to produce a patch. A future agent that returns real file
  diffs could extend `execution_bridge.py` to write those files directly
  instead of a proposal document.
- **Sandboxed commands still inherit `HOME`** (needed for git config in
  this simplified setup), which in a real deployment could mean agent
  git operations use whatever credential helper/SSH key the host
  operator has configured — fine for the disposable-repo tests here,
  but production needs a dedicated service identity/token scoped to the
  agent's own branch namespace, not personal credentials. Flagged
  explicitly rather than silently assumed safe.
- **`/shell/{id}/kill` only affects a genuinely still-running process**
  tracked in an in-memory registry within this single process — real and
  tested (a concurrent kill request does terminate an in-flight `sleep`),
  but doesn't survive a service restart, since there's no persistent job
  queue in this phase.

## Next

Phase 7: Database Connector + Database Agent — the deferred, higher-
blast-radius execution path for actual data writes, kept separate from
this phase specifically because of that distinct risk profile.
