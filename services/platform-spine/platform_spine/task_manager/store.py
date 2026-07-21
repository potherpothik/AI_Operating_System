from sqlalchemy.orm import Session
from platform_spine.models import Task, TaskEvent
from platform_spine.task_manager.state_machine import validate_transition, InvalidTransition


def enqueue(
    db: Session,
    title: str,
    description: str,
    requested_by: str,
    correlation_id: str,
    priority: str = "normal",
    context_refs: str = "",
    parent_task_id: str = None,
    conversation_id: str = None,
) -> Task:
    task = Task(
        title=title,
        description=description,
        requested_by=requested_by,
        correlation_id=correlation_id,
        priority=priority,
        status="queued",
        context_refs=context_refs,
        parent_task_id=parent_task_id,
        conversation_id=conversation_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    db.add(TaskEvent(task_id=task.id, from_status=None, to_status="queued", actor=requested_by, detail="task created"))
    db.commit()
    return task


def update_status(db: Session, task_id: str, to_status: str, actor: str, detail: str = ""):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        return None, "task not found"

    try:
        validate_transition(task.status, to_status)
    except InvalidTransition as e:
        return None, str(e)

    from_status = task.status
    task.status = to_status
    db.commit()
    db.refresh(task)

    db.add(TaskEvent(task_id=task_id, from_status=from_status, to_status=to_status, actor=actor, detail=detail))
    db.commit()
    return task, None


def get_task(db: Session, task_id: str):
    return db.query(Task).filter(Task.id == task_id).first()


def list_tasks(db: Session, status: str = None, requested_by: str = None, conversation_id: str = None, limit: int = 100):
    q = db.query(Task)
    if status:
        q = q.filter(Task.status == status)
    if requested_by:
        q = q.filter(Task.requested_by == requested_by)
    if conversation_id:
        q = q.filter(Task.conversation_id == conversation_id)
    return q.order_by(Task.created_at.desc()).limit(limit).all()


def dequeue(db: Session, agent_capability: str = None, limit: int = 10):
    """Tasks ready for planning/pickup — queued, oldest first. Planner (Phase 8) is the intended caller."""
    q = db.query(Task).filter(Task.status == "queued")
    if agent_capability:
        q = q.filter(Task.agent_capability == agent_capability)
    return q.order_by(Task.created_at.asc()).limit(limit).all()


def task_events(db: Session, task_id: str):
    return db.query(TaskEvent).filter(TaskEvent.task_id == task_id).order_by(TaskEvent.ts.asc()).all()
