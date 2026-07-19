from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from planning.db import get_db
from planning import clients
from planning.planner import store, graph_builder, replan as replan_module

router = APIRouter(prefix="/planner", tags=["planner"])


def _subtask_out(s) -> dict:
    return {
        "id": s.id, "subtask_id": s.subtask_id, "description": s.description,
        "agent_capability": s.agent_capability, "depends_on": s.depends_on,
        "status": s.status, "platform_task_id": s.platform_task_id,
    }


def _graph_out(graph, subtasks: list) -> dict:
    return {
        "task_graph_id": graph.id,
        "task_id": graph.task_id,
        "outcome": graph.outcome,
        "planning_confidence": graph.planning_confidence,
        "needs_clarification": graph.needs_clarification,
        "clarification_question": graph.clarification_question,
        "reasoning_execution_id": graph.reasoning_execution_id,
        "subtasks": [_subtask_out(s) for s in subtasks],
        "created_at": graph.created_at.isoformat(),
        "superseded_by": graph.superseded_by,
    }


class PlanRequest(BaseModel):
    task_id: str
    title: str
    description: str = ""
    requested_by: str = "human_admin"
    context_refs: str = ""
    correlation_id: Optional[str] = None


@router.post("/plan")
def plan(req: PlanRequest, db: Session = Depends(get_db)):
    task_description = f"{req.title}\n\n{req.description}".strip()
    try:
        execution = clients.execute_reasoning(req.task_id, task_description, "planner", correlation_id=req.correlation_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"reasoning engine unreachable: {e}")

    result = graph_builder.build_graph_from_execution(db, req.task_id, execution, correlation_id=req.correlation_id or "")
    return _graph_out(result["task_graph"], result["subtasks"])


class ReplanRequest(BaseModel):
    task_id: str
    original_description: str
    reason: str
    correlation_id: Optional[str] = None


@router.post("/replan")
def replan_endpoint(req: ReplanRequest, db: Session = Depends(get_db)):
    result = replan_module.replan(db, req.task_id, req.original_description, req.reason, correlation_id=req.correlation_id or "")
    return _graph_out(result["task_graph"], result["subtasks"])


@router.get("/capabilities")
def capabilities_debug():
    """Introspection: what Planner is actually reasoning over right now — useful for debugging routing decisions (Phase 8 doc)."""
    try:
        roster = clients.fetch_agent_capabilities()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"agents service unreachable: {e}")
    return {"capabilities": roster}


@router.get("/{task_graph_id}")
def get_plan(task_graph_id: str, db: Session = Depends(get_db)):
    graph = store.get_graph(db, task_graph_id)
    if not graph:
        raise HTTPException(status_code=404, detail="task graph not found")
    subtasks = store.get_subtasks(db, task_graph_id)
    return _graph_out(graph, subtasks)
