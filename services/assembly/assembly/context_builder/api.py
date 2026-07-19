from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from assembly.db import get_db
from assembly.context_builder import store

router = APIRouter(prefix="/context", tags=["context"])


class BuildRequest(BaseModel):
    task_id: str
    task_description: str
    agent_capability: str
    target_model: str
    namespace: str
    budget_words: int = store.DEFAULT_BUDGET_WORDS


class PinRequest(BaseModel):
    namespace: str
    content: str
    pinned_by: str
    agent_capability: str = None


def _package_out(package, items=None):
    out = {
        "id": package.id,
        "task_id": package.task_id,
        "agent_capability": package.agent_capability,
        "target_model": package.target_model,
        "classification_ceiling": package.classification_ceiling,
        "budget_used": package.budget_used,
        "budget_total": package.budget_total,
        "partial": package.partial,
        "created_at": package.created_at.isoformat(),
    }
    if items is not None:
        out["items"] = [
            {"source_type": i.source_type, "source_id": i.source_id, "content": i.content, "provenance": i.provenance, "included_reason": i.included_reason}
            for i in items
        ]
    return out


@router.post("/build")
def build_context(req: BuildRequest, db: Session = Depends(get_db)):
    package = store.build(
        db, req.task_id, req.task_description, req.agent_capability, req.target_model, req.namespace, req.budget_words
    )
    return _package_out(package)


@router.get("/{context_id}")
def get_context(context_id: str, db: Session = Depends(get_db)):
    result = store.get_package(db, context_id)
    if not result:
        raise HTTPException(status_code=404, detail="not found")
    package, items = result
    return _package_out(package, items)


@router.post("/pin")
def pin(req: PinRequest, db: Session = Depends(get_db)):
    fact = store.pin_fact(db, req.namespace, req.content, req.pinned_by, req.agent_capability)
    return {"id": fact.id, "pinned": True}
