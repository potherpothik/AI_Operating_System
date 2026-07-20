import datetime
from sqlalchemy.orm import Session

from execution.shell_executor.models import SandboxExecution


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def create_running(db: Session, sandbox_id: str, task_id: str, requesting_capability: str, command: str,
                    args: list, working_dir: str, mode: str, correlation_id: str = None) -> SandboxExecution:
    execution = SandboxExecution(
        id=sandbox_id,
        task_id=task_id,
        requesting_capability=requesting_capability,
        command=command,
        args=args,
        working_dir=working_dir,
        mode=mode,
        status="running",
        correlation_id=correlation_id,
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    return execution


def finalize(db: Session, sandbox_id: str, status: str, exit_code, stdout: str, stderr: str, duration_ms: int, backend: str) -> SandboxExecution | None:
    execution = db.query(SandboxExecution).filter(SandboxExecution.id == sandbox_id).first()
    if not execution:
        return None
    execution.status = status
    execution.exit_code = exit_code
    execution.stdout = stdout
    execution.stderr = stderr
    execution.duration_ms = duration_ms
    execution.backend = backend
    execution.completed_at = _now()
    db.commit()
    db.refresh(execution)
    return execution


def mark_killed(db: Session, sandbox_id: str) -> SandboxExecution | None:
    execution = db.query(SandboxExecution).filter(SandboxExecution.id == sandbox_id).first()
    if not execution:
        return None
    execution.status = "killed"
    execution.completed_at = _now()
    db.commit()
    db.refresh(execution)
    return execution


def get(db: Session, sandbox_id: str) -> SandboxExecution | None:
    return db.query(SandboxExecution).filter(SandboxExecution.id == sandbox_id).first()


def list_executions(db: Session, requesting_capability: str = None, status: str = None) -> list[SandboxExecution]:
    """Phase 13: Metrics Dashboard's tool-execution-volume-by-capability
    category — no listing endpoint existed before this, only per-id status."""
    query = db.query(SandboxExecution)
    if requesting_capability:
        query = query.filter(SandboxExecution.requesting_capability == requesting_capability)
    if status:
        query = query.filter(SandboxExecution.status == status)
    return query.order_by(SandboxExecution.created_at.desc()).all()
