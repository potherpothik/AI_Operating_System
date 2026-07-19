from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from knowledge.db import get_db
from knowledge.memory_manager import store
from knowledge.memory_manager.retention import RETENTION_POLICY, policy_for

router = APIRouter(prefix="/memory", tags=["memory"])


class WriteRequest(BaseModel):
    namespace: str
    key: str
    value: str
    actor: str
    classification_hint: str = "internal"


class QueryRequest(BaseModel):
    namespace: str
    text: str
    requester_ceiling: str = "confidential"
    limit: int = 20


@router.post("/{memory_type}/write")
def write_memory(memory_type: str, req: WriteRequest, db: Session = Depends(get_db)):
    try:
        record, outcome = store.write(
            db, memory_type, req.namespace, req.key, req.value, req.actor, req.classification_hint
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "id": record.id,
        "status": outcome["status"],
        "classification": record.classification,
        **({"approval_id": outcome["approval_id"]} if "approval_id" in outcome else {}),
    }


@router.get("/{memory_type}/read")
def read_memory(memory_type: str, namespace: str, key: str, requester_ceiling: str = "confidential", db: Session = Depends(get_db)):
    try:
        policy_for(memory_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    record = store.read(db, memory_type, namespace, key, requester_ceiling)
    if not record:
        raise HTTPException(status_code=404, detail="not found or not visible at this classification ceiling")
    return {"id": record.id, "value": record.value, "classification": record.classification, "created_at": record.created_at.isoformat()}


@router.post("/{memory_type}/query")
def query_memory(memory_type: str, req: QueryRequest, db: Session = Depends(get_db)):
    try:
        policy_for(memory_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if memory_type == "knowledge_cache":
        # Delegate to Vector Search's real semantic query rather than
        # reimplementing retrieval here — knowledge_cache is explicitly
        # vector-backed per the design doc.
        from knowledge.vector_search import index as vector_index

        hits = vector_index.query(db, req.text, namespace=req.namespace, classification_ceiling=req.requester_ceiling, top_k=req.limit)
        return {"backend": "vector_search", "hits": hits}

    rows = store.query_text(db, memory_type, req.namespace, req.text, req.requester_ceiling, req.limit)
    return {
        "backend": "substring_match",
        "hits": [{"id": r.id, "value": r.value, "classification": r.classification} for r in rows],
    }


@router.delete("/{memory_type}/{record_id}")
def delete_memory(memory_type: str, record_id: str, db: Session = Depends(get_db)):
    ok, reason = store.delete(db, memory_type, record_id)
    if not ok:
        code = 400 if "not deletable" in reason else 404
        raise HTTPException(status_code=code, detail=reason)
    return {"deleted": True}


@router.get("/{memory_type}/retention-policy")
def retention_policy(memory_type: str):
    try:
        return {"memory_type": memory_type, "policy": policy_for(memory_type)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/types")
def list_memory_types():
    return {"memory_types": list(RETENTION_POLICY.keys())}


@router.post("/{memory_type}/reconcile-approvals")
def reconcile(memory_type: str, db: Session = Depends(get_db)):
    updated = store.reconcile_pending_approvals(db, memory_type)
    return {"updated": [{"id": r.id, "status": r.status} for r in updated]}
