import os

from agents import clients

# Phase 29: governed `manage.py` invocation through Shell Executor's
# existing allowlist mechanism (services/execution/execution/shell_executor/allowlists/django_agent.yaml)
# — no new execution engine, the same real subprocess sandbox every
# other agent's shell-executing action already goes through.
TOOL_ACTIONS = {"django.check_project"}

_ALLOWED_SUBCOMMANDS = {"check", "showmigrations", "test"}

# A real Django project root, configured once per deployment — never
# taken from model output, same "the system computes the real target,
# never trusts model input for it" discipline SHELL_WORKING_DIR/
# CALC_WORKING_DIR already established.
DJANGO_PROJECT_ROOT = os.environ.get("DJANGO_PROJECT_ROOT")


def handle_tool_call(parsed: dict, agent_capability: str, task_id: str, correlation_id: str = None) -> dict:
    subcommand = (parsed.get("manage_py_command") or "").strip()
    if subcommand not in _ALLOWED_SUBCOMMANDS:
        return {"summary": f"manage_py_command must be one of {sorted(_ALLOWED_SUBCOMMANDS)}, got {subcommand!r}"}

    if not DJANGO_PROJECT_ROOT:
        return {"summary": "DJANGO_PROJECT_ROOT not configured — cannot run a real manage.py command"}

    result = clients.shell_execute(
        command="python3", args=["manage.py", subcommand], working_dir=DJANGO_PROJECT_ROOT, capability=agent_capability,
        requesting_agent="reasoning_engine", task_id=task_id, mode="read_only", correlation_id=correlation_id or "",
    )
    if not result.get("ok"):
        return {"summary": f"manage.py {subcommand} failed to run: {result.get('error')}"}

    body = result["result"]
    stdout = (body.get("stdout") or "")[:3000]
    stderr = (body.get("stderr") or "")[:1000]
    return {
        "summary": f"manage.py {subcommand}: exit_code={body.get('exit_code')}, status={body.get('status')}, "
                   f"stdout: {stdout}" + (f", stderr: {stderr}" if stderr else ""),
    }
