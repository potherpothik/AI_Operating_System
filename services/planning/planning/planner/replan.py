from sqlalchemy.orm import Session

from planning import clients
from planning.planner import store, graph_builder


def replan(db: Session, task_id: str, original_description: str, reason: str, correlation_id: str = "") -> dict:
    """
    Handles the re-planning trigger the Phase 8 doc names: a subtask came
    back refused, a delegate_request named a capability that doesn't
    exist, or a downstream approval was rejected. The failure reason is
    folded into the task description as real context for the new
    planning pass — not just retried blind — and the old graph is marked
    superseded rather than deleted, so "why was this restructured" stays
    answerable.
    """
    old_graph = store.get_latest_graph_for_task(db, task_id)

    augmented_description = (
        f"{original_description}\n\n"
        f"[System: a previous plan for this task failed during execution: {reason}. "
        f"Produce a revised plan that accounts for this — route around the failure, "
        f"or report needs_clarification / no_capability_found if it can't be worked around.]"
    )

    execution = clients.execute_reasoning(task_id, augmented_description, "planner", correlation_id=correlation_id)
    result = graph_builder.build_graph_from_execution(db, task_id, execution, correlation_id=correlation_id)

    if old_graph:
        store.supersede(db, old_graph.id, result["task_graph"].id)

    return result
