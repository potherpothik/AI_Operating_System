import json
import os

from agents import clients

# Both of this phase's genuinely-executing actions — docker.inspect
# (Phase 10, Section 4) and testing.run_suite (Section 5) — get the same
# non-terminal tool-call treatment database_bridge.py established for
# db.read/db.dry_run: Reasoning Engine runs the real command, feeds the
# actual result back into context, and continues iterating rather than
# trusting the model's guess about what a shell command would return.
TOOL_ACTIONS = {"docker.inspect", "testing.run_suite"}

# A real working_dir under Shell Executor's own SANDBOX_ROOT — configured
# once per deployment, same pattern as execution_bridge.py's
# PROPOSAL_REPO_PATH, never taken from model output. A model that could
# pick its own working_dir would be choosing its own sandbox confinement.
SHELL_WORKING_DIR = os.environ.get("SHELL_WORKING_DIR", os.environ.get("PROPOSAL_REPO_PATH", "/tmp/ai_os_sandbox"))


def _parse_args(parsed: dict) -> tuple[list, str | None]:
    raw = parsed.get("shell_args_json") or "[]"
    try:
        args = json.loads(raw)
    except json.JSONDecodeError as e:
        return [], f"shell_args_json was not valid JSON ({e})"
    if not isinstance(args, list):
        return [], "shell_args_json must be a JSON array"
    return args, None


def handle_tool_call(parsed: dict, agent_capability: str, task_id: str, correlation_id: str = None) -> dict:
    action = parsed.get("action")
    command = (parsed.get("shell_command") or "").strip()
    args, arg_error = _parse_args(parsed)
    if arg_error:
        return {"summary": arg_error}
    if not command:
        return {"summary": "shell_command was empty — nothing to run"}

    if action == "testing.run_suite":
        # Structural, not a policy convention: verified fresh before every
        # single run, never cached or assumed from a prior verification.
        resolved_environment = (parsed.get("resolved_environment") or "").strip()
        verify = clients.verify_environment(resolved_environment, agent_capability, correlation_id=correlation_id or "")
        if not verify.get("ok"):
            return {"summary": f"environment verification denied: {verify.get('error')} — refusing to run testing.run_suite"}

    result = clients.shell_execute(
        command=command, args=args, working_dir=SHELL_WORKING_DIR, capability=agent_capability,
        requesting_agent="reasoning_engine", task_id=task_id, mode="read_only", correlation_id=correlation_id or "",
    )
    if not result.get("ok"):
        return {"summary": f"shell execution failed: {result.get('error')}"}

    body = result["result"]
    stdout = (body.get("stdout") or "")[:3000]
    return {
        "summary": f"exit_code={body.get('exit_code')}, status={body.get('status')}, stdout: {stdout}",
    }
