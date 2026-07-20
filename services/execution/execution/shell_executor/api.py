from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from execution.db import get_db
from execution.shell_executor import store
from execution.shell_executor.service import run_sandboxed, Denied
from execution.shell_executor.sandbox import get_sandbox

router = APIRouter(prefix="/shell", tags=["shell"])


class ExecuteRequest(BaseModel):
    command: str
    args: list[str] = []
    working_dir: str
    capability: str
    requesting_agent: str
    task_id: str = None
    mode: str  # read_only | mutating
    correlation_id: str = None
    timeout_seconds: int = None
    network: bool = False


def execution_out(execution) -> dict:
    return {
        "sandbox_id": execution.id,
        "task_id": execution.task_id,
        "requesting_capability": execution.requesting_capability,
        "status": execution.status,
        "exit_code": execution.exit_code,
        "stdout": execution.stdout,
        "stderr": execution.stderr,
        "duration_ms": execution.duration_ms,
        "backend": execution.backend,
        "created_at": execution.created_at.isoformat(),
        "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
    }


@router.post("/execute")
def execute(req: ExecuteRequest, db: Session = Depends(get_db)):
    try:
        execution = run_sandboxed(
            db, req.command, req.args, req.working_dir, req.capability, req.requesting_agent,
            task_id=req.task_id, mode=req.mode, correlation_id=req.correlation_id,
            timeout_seconds=req.timeout_seconds, network=req.network,
        )
    except Denied as e:
        raise HTTPException(status_code=403, detail=str(e))
    return execution_out(execution)


@router.get("/executions")
def list_executions(requesting_capability: str = None, status: str = None, db: Session = Depends(get_db)):
    """Phase 13: Metrics Dashboard's tool-execution-volume-by-capability
    category — no listing endpoint existed before this, only per-id status."""
    executions = store.list_executions(db, requesting_capability=requesting_capability, status=status)
    return [execution_out(e) for e in executions]


@router.get("/{sandbox_id}/status")
def status(sandbox_id: str, db: Session = Depends(get_db)):
    execution = store.get(db, sandbox_id)
    if not execution:
        raise HTTPException(status_code=404, detail="sandbox execution not found")
    return execution_out(execution)


@router.post("/{sandbox_id}/kill")
def kill(sandbox_id: str, db: Session = Depends(get_db)):
    execution = store.get(db, sandbox_id)
    if not execution:
        raise HTTPException(status_code=404, detail="sandbox execution not found")

    sandbox = get_sandbox()
    was_running = sandbox.kill(sandbox_id)
    if was_running:
        execution = store.mark_killed(db, sandbox_id)
    return {"sandbox_id": sandbox_id, "was_running": was_running, "status": execution.status}
