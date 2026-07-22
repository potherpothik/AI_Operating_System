from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from planning.db import get_db
from planning import clients
from planning.planner import store
from planning.workflows import store as workflow_store, dispatcher

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _subtask_out(s) -> dict:
    return {
        "id": s.id, "subtask_id": s.subtask_id, "description": s.description,
        "agent_capability": s.agent_capability, "depends_on": s.depends_on,
        "status": s.status, "platform_task_id": s.platform_task_id,
        "reasoning_execution_id": s.reasoning_execution_id,
    }


def _run_out(graph, subtasks: list) -> dict:
    return {
        "task_graph_id": graph.id,
        "task_id": graph.task_id,
        "workflow": graph.outcome,  # trigger() stores the workflow name as the graph's outcome — see trigger() below
        "subtasks": [_subtask_out(s) for s in subtasks],
        "created_at": graph.created_at.isoformat(),
    }


@router.get("")
def list_workflows():
    try:
        return {"workflows": workflow_store.list_workflows()}
    except workflow_store.WorkflowNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except workflow_store.WorkflowDefinitionInvalid as e:
        raise HTTPException(status_code=500, detail=str(e))


class TriggerRequest(BaseModel):
    correlation_id: Optional[str] = None


@router.post("/{name}/trigger")
def trigger_workflow(name: str, req: TriggerRequest = TriggerRequest(), db: Session = Depends(get_db)):
    """
    Real trigger: loads the saved workflow definition, creates one real
    parent Task Manager task plus one real Task Manager task per step
    (mirroring graph_builder.build_graph_from_execution's own pattern
    exactly), persists the whole graph via Phase 8's own TaskGraph/Subtask
    schema, then dispatches whatever steps have no depends_on right now.
    No authorize() call here — same posture as /planner/plan: the real
    governance gate is each step's own execute_reasoning() call, unchanged.
    """
    try:
        workflow = workflow_store.get_workflow(name)
    except workflow_store.WorkflowNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except workflow_store.WorkflowNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))

    correlation_id = req.correlation_id or ""
    parent_task = clients.create_subtask(
        title=f"[workflow] {workflow['workflow']}", description=workflow.get("description", ""),
        correlation_id=correlation_id,
    )
    task_id = parent_task.get("id") or f"workflow-{workflow['workflow']}"

    graph = store.create_graph(
        db, task_id, outcome=workflow["workflow"], planning_confidence=None,
        needs_clarification=False, clarification_question=None, reasoning_execution_id=None,
    )

    for step in workflow["steps"]:
        platform_task = clients.create_subtask(
            title=f"[{step['agent_capability']}] {step['description'][:80]}",
            description=step["description"], correlation_id=correlation_id, parent_task_id=task_id,
        )
        store.add_subtask(
            db, graph.id, step["subtask_id"], step["description"], step["agent_capability"],
            step.get("depends_on", []), platform_task_id=platform_task.get("id"),
        )

    dispatched = dispatcher.dispatch_ready_subtasks(db, graph.id, correlation_id)
    subtasks = store.get_subtasks(db, graph.id)
    return {**_run_out(graph, subtasks), "dispatched": dispatched}


@router.post("/runs/{task_graph_id}/advance")
def advance_run(task_graph_id: str, req: TriggerRequest = TriggerRequest(), db: Session = Depends(get_db)):
    graph = store.get_graph(db, task_graph_id)
    if not graph:
        raise HTTPException(status_code=404, detail="workflow run not found")
    advanced = dispatcher.advance(db, task_graph_id, req.correlation_id or "")
    subtasks = store.get_subtasks(db, task_graph_id)
    return {**_run_out(graph, subtasks), "advanced": advanced}


@router.get("/runs/{task_graph_id}")
def get_run(task_graph_id: str, db: Session = Depends(get_db)):
    graph = store.get_graph(db, task_graph_id)
    if not graph:
        raise HTTPException(status_code=404, detail="workflow run not found")
    subtasks = store.get_subtasks(db, task_graph_id)
    return _run_out(graph, subtasks)
