import uuid
from sqlalchemy.orm import Session

from execution import clients
from execution.shell_executor import allowlist, store
from execution.shell_executor.sandbox import get_sandbox, WorkingDirNotAllowed, SandboxCreationError


class Denied(Exception):
    pass


def run_sandboxed(db: Session, command: str, args: list, working_dir: str, capability: str, requesting_agent: str,
                   task_id: str = None, mode: str = "read_only", correlation_id: str = None,
                   timeout_seconds: int = None, network: bool = False, extra_env: dict = None):
    """
    The core of Shell Executor, callable directly (Git Manager, in the
    same process, uses this — not a self-HTTP-call) or via POST
    /shell/execute. Security Layer authorization and allow-list
    enforcement happen here either way; no caller gets to skip them by
    calling in-process instead of over HTTP.
    """
    decision = clients.authorize(
        actor=capability, action="shell.execute", resource=working_dir, correlation_id=correlation_id or "",
    )
    if decision["decision"] == "deny":
        clients.audit_log(
            actor_id=capability, action="shell.execute", resource=working_dir,
            decision="deny", reason=decision.get("reason", ""), correlation_id=correlation_id or "",
        )
        raise Denied(decision.get("reason", "denied by security layer"))

    allowed, reason = allowlist.check(capability, command, args, mode)
    if not allowed:
        clients.audit_log(
            actor_id=capability, action="shell.execute", resource=f"{command} {' '.join(args)}",
            decision="deny", reason=reason, correlation_id=correlation_id or "",
        )
        raise Denied(reason)

    sandbox_id = str(uuid.uuid4())
    store.create_running(db, sandbox_id, task_id, capability, command, args, working_dir, mode, correlation_id)

    sandbox = get_sandbox()
    try:
        result = sandbox.run(command, args, working_dir, mode, timeout_seconds=timeout_seconds, network=network, sandbox_id=sandbox_id, extra_env=extra_env)
    except (WorkingDirNotAllowed, SandboxCreationError) as e:
        execution = store.finalize(db, sandbox_id, "failed", None, "", str(e), 0, "none")
        clients.audit_log(
            actor_id=capability, action="shell.execute", resource=command,
            decision="failed", reason=str(e), correlation_id=correlation_id or "",
        )
        return execution

    status = "timed_out" if result.timed_out else "completed"
    execution = store.finalize(db, sandbox_id, status, result.exit_code, result.stdout, result.stderr, result.duration_ms, result.backend)

    clients.audit_log(
        actor_id=capability, action="shell.execute", resource=f"{command} {' '.join(args)}",
        decision=status, reason=f"exit_code={result.exit_code}", correlation_id=correlation_id or "",
    )
    return execution
