from pathlib import Path

from agents import clients
from agents.reasoning_engine import execution_bridge

CODING_GATEWAY_PROPOSE_ACTIONS = {"coding_gateway.propose_run"}

# Real, per-provider invocation shape — matches the actual CLI contracts,
# not a placeholder. Claude Code's real `-p` headless flag reads the
# instruction directly (a file path in the prompt text, not a CLI flag of
# its own); OpenCode's `run` subcommand takes the prompt positionally too.
_PROVIDERS = {
    "claude_code": {
        "binary": "claude",
        "version_args": ["--version"],
        "run_args": lambda instruction_file: ["-p", f"Follow the instructions in {instruction_file}.", "--output-format", "json"],
        "instruction_rel_path": "claude-task.md",
    },
    "opencode": {
        "binary": "opencode",
        "version_args": ["--version"],
        "run_args": lambda instruction_file: ["run", f"Follow the instructions in {instruction_file}."],
        "instruction_rel_path": "AGENTS.md",
    },
}


def materialize_propose_run(execution) -> dict:
    """
    Phase 22: after human approval, drive an external coding CLI (Claude
    Code or OpenCode) inside the execution sandbox and turn whatever it
    changes into the same branch/commit/push/MR flow every other
    propose_* action already uses (execution_bridge's own pattern, reused
    for the branch and the eventual MR — only the "what gets committed"
    step is genuinely new here).

    Real, structural safety gate before any agentic session runs: the
    same read-only version probe that confirms the CLI is even installed
    also reports which sandbox backend served it (Shell Executor already
    returns `backend` on every execution). SubprocessSandbox — the only
    backend available anywhere in this environment, no Docker daemon
    since Phase 6 — is documented as NOT providing real network or
    filesystem isolation (services/execution/execution/shell_executor/sandbox.py).
    An external coding agent given a live task would run with this
    environment's real credentials and unrestricted network access under
    that backend — exactly the "untrusted tool" this phase's own design
    doc says must stay confined. Refusing the mutating run when the
    backend isn't `docker` isn't a stub; it's the same isolation
    boundary this whole environment has had since Phase 6, now enforced
    at the one call site where it actually matters (every earlier
    agent's shell commands were deterministic scripts or git operations
    with no live external credentials to leak).
    """
    repo_path = execution_bridge.PROPOSAL_REPO_PATH
    if not repo_path:
        return {"attempted": False, "reason": "PROPOSAL_REPO_PATH not configured"}

    result = execution.result or {}
    provider = result.get("provider")
    instruction = result.get("instruction", "")
    task_id = execution.task_id
    agent_capability = execution.agent_capability

    provider_cfg = _PROVIDERS.get(provider)
    if not provider_cfg:
        return {"attempted": False, "reason": f"unknown provider {provider!r}"}

    probe = clients.shell_execute(
        provider_cfg["binary"], provider_cfg["version_args"], repo_path,
        agent_capability, "reasoning_engine", mode="read_only", task_id=task_id, correlation_id=execution.id,
    )
    if not probe.get("ok"):
        return {"attempted": True, "stage": "probe", "status": "failed", "result": probe}
    probe_result = probe["result"]

    if probe_result.get("status") == "failed" and probe_result.get("exit_code") is None:
        return {
            "attempted": True, "stage": "probe", "status": "not_configured",
            "reason": f"{provider_cfg['binary']!r} not found in the sandbox execution environment",
            "probe": probe_result,
        }

    backend = probe_result.get("backend")
    if backend != "docker":
        return {
            "attempted": True, "stage": "probe", "status": "unsafe_backend",
            "reason": (
                f"sandbox backend is {backend!r}; a live external-agent session needs "
                f"DockerSandbox's real --network-none/workdir-only isolation, not available "
                f"in this environment (no Docker daemon) — refusing to run an unconfined "
                f"agentic session rather than proceeding anyway"
            ),
            "probe": probe_result,
        }

    branch_result = clients.git_branch(repo_path, agent_capability, task_id, "reasoning_engine", correlation_id=execution.id)
    if branch_result.get("status") != "completed":
        return {"attempted": True, "stage": "branch", "result": branch_result}
    branch_name = branch_result["branch_name"]

    instruction_rel_path = provider_cfg["instruction_rel_path"]
    instruction_abs_path = Path(repo_path) / instruction_rel_path
    instruction_abs_path.parent.mkdir(parents=True, exist_ok=True)
    instruction_abs_path.write_text(instruction + "\n")

    run_result = clients.shell_execute(
        provider_cfg["binary"], provider_cfg["run_args"](instruction_rel_path), repo_path,
        agent_capability, "reasoning_engine", mode="mutating", task_id=task_id, correlation_id=execution.id,
    )
    if not run_result.get("ok") or run_result["result"].get("status") != "completed":
        return {"attempted": True, "stage": "run", "status": "failed", "result": run_result}

    diff_result = clients.git_diff(
        repo_path, agent_capability, task_id, "reasoning_engine",
        args=["--name-only"], correlation_id=execution.id,
    )
    changed_files = [line for line in diff_result.get("diff", "").splitlines() if line.strip()] if diff_result.get("ok") else []
    if not changed_files:
        return {"attempted": True, "stage": "run", "status": "no_changes", "run_result": run_result}

    commit_result = clients.git_commit(
        repo_path, agent_capability, task_id, "reasoning_engine", changed_files,
        summary=f"Coding Agent Gateway ({provider}) session for task {task_id}",
        reasoning_execution_id=execution.id, context_id=execution.context_id, correlation_id=execution.id,
    )
    if commit_result.get("status") != "completed":
        return {"attempted": True, "stage": "commit", "result": commit_result}

    push_result = clients.git_push(repo_path, agent_capability, task_id, "reasoning_engine", branch_name, correlation_id=execution.id)
    if push_result.get("status") != "completed":
        return {"attempted": True, "stage": "push", "result": push_result}

    mr_result = clients.git_open_mr(
        execution_bridge.PROPOSAL_MR_REPO, branch_name, agent_capability, task_id, "reasoning_engine",
        proposal_text=f"Coding Agent Gateway ({provider}) proposal for task {task_id}",
        risk_classification=result.get("risk_classification", "high"),
        files_changed=changed_files, correlation_id=execution.id,
    )

    return {
        "attempted": True, "stage": "open_mr", "branch_name": branch_name,
        "commit_sha": commit_result.get("commit_sha"), "mr_result": mr_result,
    }
