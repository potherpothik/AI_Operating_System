from sqlalchemy.orm import Session

from planning.planner.models import TaskGraph, Subtask


def create_graph(db: Session, task_id: str, outcome: str, planning_confidence: float,
                  needs_clarification: bool, clarification_question: str, reasoning_execution_id: str) -> TaskGraph:
    graph = TaskGraph(
        task_id=task_id, outcome=outcome, planning_confidence=planning_confidence,
        needs_clarification=needs_clarification, clarification_question=clarification_question,
        reasoning_execution_id=reasoning_execution_id,
    )
    db.add(graph)
    db.commit()
    db.refresh(graph)
    return graph


def add_subtask(db: Session, task_graph_id: str, subtask_id: str, description: str, agent_capability: str,
                 depends_on: list, platform_task_id: str = None) -> Subtask:
    row = Subtask(
        task_graph_id=task_graph_id, subtask_id=subtask_id, description=description,
        agent_capability=agent_capability, depends_on=depends_on or [], platform_task_id=platform_task_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_graph(db: Session, graph_id: str) -> TaskGraph | None:
    return db.query(TaskGraph).filter(TaskGraph.id == graph_id).first()


def get_subtasks(db: Session, graph_id: str) -> list[Subtask]:
    return db.query(Subtask).filter(Subtask.task_graph_id == graph_id).all()


def get_latest_graph_for_task(db: Session, task_id: str) -> TaskGraph | None:
    return (
        db.query(TaskGraph)
        .filter(TaskGraph.task_id == task_id, TaskGraph.superseded_by.is_(None))
        .order_by(TaskGraph.created_at.desc())
        .first()
    )


def supersede(db: Session, old_graph_id: str, new_graph_id: str):
    old = db.query(TaskGraph).filter(TaskGraph.id == old_graph_id).first()
    if old:
        old.superseded_by = new_graph_id
        db.commit()
