from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from agents.db import get_db
from agents.reasoning_engine import loop, store

router = APIRouter(prefix="/reasoning", tags=["reasoning"])


class ExecuteRequest(BaseModel):
    task_id: str
    task_description: str
    agent_capability: str
    namespace: str = "default"
    # Explicit Optional[...] rather than bare "str = None" — in Pydantic
    # v2, "str = None" only sets the default, it does NOT widen the type
    # to accept an explicit `null` in the request body. Found live: a
    # caller that sends target_model: null (rather than omitting the
    # field entirely) got a 422 even though the field is meant to be
    # optional. Any caller relying on omission alone worked by accident.
    target_model: Optional[str] = None
    max_iterations: Optional[int] = None
    correlation_id: Optional[str] = None


def _execution_out(execution) -> dict:
    return {
        "id": execution.id,
        "task_id": execution.task_id,
        "context_id": execution.context_id,
        "agent_capability": execution.agent_capability,
        "target_model": execution.target_model,
        "status": execution.status,
        "result": execution.result,
        "approval_id": execution.approval_id,
        "delegate_task_id": execution.delegate_task_id,
        "failure_reason": execution.failure_reason,
        "iterations_used": execution.iterations_used,
        "max_iterations": execution.max_iterations,
        "created_at": execution.created_at.isoformat(),
        "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
    }


@router.post("/execute")
def execute(req: ExecuteRequest, db: Session = Depends(get_db)):
    try:
        execution = loop.execute(
            db, req.task_id, req.task_description, req.agent_capability, req.namespace,
            target_model=req.target_model, max_iterations=req.max_iterations, correlation_id=req.correlation_id,
        )
    except loop.UnknownCapability as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _execution_out(execution)


@router.get("/{execution_id}/trace")
def trace(execution_id: str, db: Session = Depends(get_db)):
    execution = store.get_execution(db, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="execution not found")
    steps = store.get_steps(db, execution_id)
    return {
        "execution": _execution_out(execution),
        "steps": [
            {
                "iteration": s.iteration,
                "prompt_ref": s.prompt_ref,
                "raw_response": s.raw_response,
                "parsed_decision": s.parsed_decision,
                "routing_outcome": s.routing_outcome,
                "ts": s.ts.isoformat(),
            }
            for s in steps
        ],
    }


@router.post("/{execution_id}/resume")
def resume(execution_id: str, db: Session = Depends(get_db)):
    execution = loop.resume(db, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="execution not found")
    return _execution_out(execution)
