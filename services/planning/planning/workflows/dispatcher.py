from sqlalchemy.orm import Session

from planning import clients
from planning.planner import store

# Phase 30: this system has never had a background task consumer, at any
# phase — Task Manager's own dequeue() (Phase 2) has had zero real
# callers since it was written, and Planner's own subtasks (Phase 8)
# have always just sat at status="planned" forever, since nothing ever
# advanced them. Every real agent execution anywhere in this system has
# always been an explicit, synchronous call to POST /reasoning/execute
# by whatever wants it to happen right now (Planner calling it for
# itself; MCP Surface's ask_agent calling it for a human's question).
# This dispatcher follows that same, already-established pattern rather
# than inventing a background scheduler this project has never had:
# dispatching and advancing a workflow are both explicit calls, not an
# ambient process. "Never batches consent" falls out of this for free —
# each subtask's own real governance gate (its capability's policy role)
# is the same one every non-workflow execution of that capability
# already goes through, since dispatch is exactly the same
# execute_reasoning() call Planner's own flow uses.

_TERMINAL_STATUSES = {"done", "failed"}


def _map_execution_status(execution: dict) -> str:
    status = execution.get("status")
    if status == "completed":
        return "done"
    if status == "awaiting_approval":
        return "awaiting_approval"
    # refused | rejected | failed | awaiting_delegation — all real,
    # distinct outcomes, but a workflow step chasing a delegation chain
    # or arguing with a refusal is genuinely out of this phase's scope;
    # named honestly here rather than silently retried or hidden.
    return "failed"


def dispatch_ready_subtasks(db: Session, graph_id: str, correlation_id: str = "") -> list:
    """
    Real dispatch: any subtask still "planned" whose every depends_on
    entry is already "done" gets a real, live POST /reasoning/execute
    call right now — the exact same call Planner's own flow makes for
    itself, just routed at a different capability. Runs repeatedly
    (bounded by the subtask count, so a self-referential depends_on can
    never spin forever) since dispatching one subtask can make another
    become ready in the same pass, when both resolve synchronously.
    """
    dispatched = []
    subtasks = {s.subtask_id: s for s in store.get_subtasks(db, graph_id)}

    for _ in range(len(subtasks) + 1):
        ready = [
            s for s in subtasks.values()
            if s.status == "planned" and all(subtasks[dep].status == "done" for dep in s.depends_on)
        ]
        if not ready:
            break
        for s in ready:
            try:
                execution = clients.execute_reasoning(
                    task_id=s.platform_task_id or s.id, task_description=s.description,
                    agent_capability=s.agent_capability, correlation_id=correlation_id,
                )
            except Exception as e:  # noqa: BLE001 — a real transport failure, never silently skipped
                updated = store.update_subtask_status(db, s.id, "failed")
                subtasks[s.subtask_id] = updated
                dispatched.append({"subtask_id": s.subtask_id, "error": str(e)})
                continue
            new_status = _map_execution_status(execution)
            updated = store.update_subtask_status(db, s.id, new_status, reasoning_execution_id=execution.get("id"))
            subtasks[s.subtask_id] = updated
            dispatched.append({"subtask_id": s.subtask_id, "status": new_status, "reasoning_execution_id": execution.get("id")})

    return dispatched


def advance(db: Session, graph_id: str, correlation_id: str = "") -> list:
    """
    The explicit continuation call — same posture as
    reasoning_engine/loop.py's own resume(): nothing in this system
    auto-resumes an awaiting_approval execution just because a human
    decided the approval; something has to actually call it. For every
    subtask still awaiting_approval, checks whether its real approval
    has been decided (loop.resume() is itself safe to call repeatedly —
    still-pending returns the same state unchanged, never errors), then
    dispatches whatever became newly ready as a result.
    """
    advanced = []
    for s in store.get_subtasks(db, graph_id):
        if s.status != "awaiting_approval" or not s.reasoning_execution_id:
            continue
        try:
            execution = clients.resume_reasoning(s.reasoning_execution_id)
        except Exception as e:  # noqa: BLE001
            advanced.append({"subtask_id": s.subtask_id, "error": str(e)})
            continue
        new_status = _map_execution_status(execution)
        if new_status != s.status:
            store.update_subtask_status(db, s.id, new_status)
            advanced.append({"subtask_id": s.subtask_id, "status": new_status})

    return advanced + dispatch_ready_subtasks(db, graph_id, correlation_id)
