import asyncio
import uuid
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from platform_spine.db import get_db, SessionLocal
from platform_spine.security_client import authorize
from platform_spine.task_manager import store, conversations
from platform_spine.gateway.auth import resolve_actor, resolve_actor_for_stream
from platform_spine.gateway.rate_limit import check_rate_limit

router = APIRouter(prefix="/api/v1", tags=["gateway"])


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    priority: str = "normal"
    context_refs: str = ""
    conversation_id: str = None


class ConversationCreate(BaseModel):
    title: str = "New conversation"


def _conversation_out(c) -> dict:
    return {
        "id": c.id, "title": c.title, "created_by": c.created_by,
        "created_at": c.created_at.isoformat(), "updated_at": c.updated_at.isoformat(),
        "archived_at": c.archived_at.isoformat() if c.archived_at else None,
    }


class TaskStatusUpdate(BaseModel):
    status: str
    detail: str = ""


def _task_out(task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "requested_by": task.requested_by,
        "correlation_id": task.correlation_id,
        "conversation_id": task.conversation_id,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


@router.post("/conversations")
def create_conversation(body: ConversationCreate, db: Session = Depends(get_db), actor: str = Depends(resolve_actor)):
    """
    Phase 24 gap-fill: no authorize() call — creating a conversation has
    no real-world side effect of its own (Task.conversation_id is what
    threads real orchestration, and task.create is already governed).
    """
    check_rate_limit(actor)
    conversation = conversations.create(db, title=body.title, created_by=actor)
    return _conversation_out(conversation)


@router.get("/conversations")
def list_conversations_endpoint(db: Session = Depends(get_db), actor: str = Depends(resolve_actor)):
    check_rate_limit(actor)
    rows = conversations.list_for_actor(db, created_by=actor)
    return [_conversation_out(c) for c in rows]


@router.get("/conversations/{conversation_id}")
def get_conversation_endpoint(conversation_id: str, db: Session = Depends(get_db), actor: str = Depends(resolve_actor)):
    check_rate_limit(actor)
    conversation = conversations.get(db, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="conversation not found")
    return _conversation_out(conversation)


@router.post("/tasks")
def create_task(body: TaskCreate, db: Session = Depends(get_db), actor: str = Depends(resolve_actor)):
    check_rate_limit(actor)
    correlation_id = str(uuid.uuid4())

    # AuthZ is delegated entirely to Security Layer (Phase 1) — Gateway
    # makes no allow/deny decision of its own.
    decision = authorize(actor=actor, action="task.create", resource="*", correlation_id=correlation_id)
    if decision["decision"] == "deny":
        raise HTTPException(status_code=403, detail=decision["reason"])

    task = store.enqueue(
        db,
        title=body.title,
        description=body.description,
        requested_by=actor,
        correlation_id=correlation_id,
        priority=body.priority,
        context_refs=body.context_refs,
        conversation_id=body.conversation_id,
    )
    return _task_out(task)


@router.get("/tasks/{task_id}")
def get_task_status(task_id: str, db: Session = Depends(get_db), actor: str = Depends(resolve_actor)):
    check_rate_limit(actor)
    task = store.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return _task_out(task)


@router.get("/tasks")
def list_tasks_endpoint(
    status: str = None, conversation_id: str = None, db: Session = Depends(get_db), actor: str = Depends(resolve_actor)
):
    check_rate_limit(actor)
    tasks = store.list_tasks(db, status=status, conversation_id=conversation_id)
    return [_task_out(t) for t in tasks]


@router.post("/tasks/{task_id}/status")
def update_task_status(
    task_id: str, body: TaskStatusUpdate, db: Session = Depends(get_db), actor: str = Depends(resolve_actor)
):
    check_rate_limit(actor)
    task, error = store.update_status(db, task_id, body.status, actor=actor, detail=body.detail)
    if error == "task not found":
        raise HTTPException(status_code=404, detail=error)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return _task_out(task)


@router.get("/tasks/{task_id}/events")
def get_task_events(task_id: str, db: Session = Depends(get_db), actor: str = Depends(resolve_actor)):
    """
    Phase 15: Project Management Agent's task.read tool call needs the
    full state-transition history, not just the current snapshot
    GET /tasks/{task_id} already returns — task_events() has existed in
    task_manager/store.py since Phase 2 but was never exposed over HTTP
    until now, since nothing needed it before.
    """
    check_rate_limit(actor)
    task = store.get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    events = store.task_events(db, task_id)
    return [
        {
            "id": e.id,
            "task_id": e.task_id,
            "from_status": e.from_status,
            "to_status": e.to_status,
            "actor": e.actor,
            "detail": e.detail,
            "ts": e.ts.isoformat(),
        }
        for e in events
    ]


@router.get("/tasks/{task_id}/stream")
async def stream_task_status(task_id: str, actor: str = Depends(resolve_actor_for_stream)):
    """
    Server-sent events: polls task status and yields updates until the
    task reaches a terminal state (done/failed) or the client disconnects.
    A dedicated session per poll — this runs outside the normal
    request-scoped get_db dependency since it's long-lived.
    """
    check_rate_limit(actor)

    async def event_stream():
        last_status = None
        terminal = {"done", "failed"}
        for _ in range(300):  # bounded — ~5 minutes at 1s polling, never an unbounded loop
            db = SessionLocal()
            try:
                task = store.get_task(db, task_id)
            finally:
                db.close()
            if not task:
                yield f"data: {json.dumps({'error': 'task not found'})}\n\n"
                return
            if task.status != last_status:
                yield f"data: {json.dumps(_task_out(task))}\n\n"
                last_status = task.status
            if task.status in terminal:
                return
            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
