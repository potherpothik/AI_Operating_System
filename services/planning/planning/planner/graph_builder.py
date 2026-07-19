from sqlalchemy.orm import Session

from planning import clients
from planning.planner import store


def build_graph_from_execution(db: Session, task_id: str, execution: dict, correlation_id: str = "") -> dict:
    """
    Turns Reasoning Engine's raw execution result into real TaskGraph +
    Subtask rows — and, for a genuine plan, real Task Manager subtasks
    (Phase 2), not just local bookkeeping. A subtask that fails to reach
    Task Manager is still recorded with platform_task_id=None rather than
    silently dropped, so the gap is visible in the graph itself.
    """
    status = execution.get("status")
    result = execution.get("result") or {}
    reasoning_execution_id = execution.get("id")

    if status != "completed":
        graph = store.create_graph(
            db, task_id, outcome="failed", planning_confidence=None,
            needs_clarification=False, clarification_question=None, reasoning_execution_id=reasoning_execution_id,
        )
        return {"task_graph": graph, "subtasks": [], "reason": f"reasoning execution ended in status={status!r}, not completed"}

    outcome = result.get("outcome", "failed")
    confidence = result.get("confidence")

    if outcome == "needs_clarification":
        graph = store.create_graph(
            db, task_id, outcome=outcome, planning_confidence=confidence,
            needs_clarification=True, clarification_question=result.get("clarification_question"),
            reasoning_execution_id=reasoning_execution_id,
        )
        return {"task_graph": graph, "subtasks": []}

    if outcome == "no_capability_found":
        graph = store.create_graph(
            db, task_id, outcome=outcome, planning_confidence=confidence,
            needs_clarification=False, clarification_question=None, reasoning_execution_id=reasoning_execution_id,
        )
        return {"task_graph": graph, "subtasks": []}

    if outcome != "plan":
        graph = store.create_graph(
            db, task_id, outcome="failed", planning_confidence=confidence,
            needs_clarification=False, clarification_question=None, reasoning_execution_id=reasoning_execution_id,
        )
        return {"task_graph": graph, "subtasks": [], "reason": f"unrecognized outcome {outcome!r}"}

    graph = store.create_graph(
        db, task_id, outcome="plan", planning_confidence=confidence,
        needs_clarification=False, clarification_question=None, reasoning_execution_id=reasoning_execution_id,
    )

    subtasks = []
    for raw in result.get("task_graph", []):
        platform_task = clients.create_subtask(
            title=f"[{raw.get('agent_capability')}] {raw.get('description', '')[:80]}",
            description=raw.get("description", ""),
            correlation_id=correlation_id, parent_task_id=task_id,
        )
        row = store.add_subtask(
            db, graph.id, raw.get("subtask_id", ""), raw.get("description", ""),
            raw.get("agent_capability", ""), raw.get("depends_on", []),
            platform_task_id=platform_task.get("id"),
        )
        subtasks.append(row)

    return {"task_graph": graph, "subtasks": subtasks}
