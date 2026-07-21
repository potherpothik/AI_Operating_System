from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from knowledge.db import get_db
from knowledge.vector_search import index
from knowledge.vector_search.index import EmbeddingDimensionMismatch

router = APIRouter(prefix="/vector", tags=["vector"])


class IngestRequest(BaseModel):
    source: str
    content: str
    project_id: str
    doc_type: str = "generic"
    classification: str = "internal"
    version: str = "1"


class QueryRequest(BaseModel):
    text: str
    namespace: str = None
    classification_ceiling: str = "confidential"
    doc_type: str = None
    top_k: int = 5


class ReindexRequest(BaseModel):
    content: str


@router.post("/ingest")
def ingest_document(req: IngestRequest, db: Session = Depends(get_db)):
    result = index.ingest(db, req.source, req.content, req.project_id, req.doc_type, req.classification, req.version)
    return result


@router.post("/query")
def query_vectors(req: QueryRequest, db: Session = Depends(get_db)):
    try:
        hits = index.query(db, req.text, req.namespace, req.classification_ceiling, req.doc_type, req.top_k)
    except EmbeddingDimensionMismatch as e:
        # Phase 25: a real corpus-state conflict — the embedding backend
        # changed since some of these documents were indexed. A clear
        # 409, not a raw 500, and never a silently wrong ranking.
        raise HTTPException(status_code=409, detail=str(e))
    return {"hits": hits}


@router.delete("/{document_id}")
def delete_document(document_id: str, db: Session = Depends(get_db)):
    ok = index.delete_document(db, document_id)
    if not ok:
        raise HTTPException(status_code=404, detail="not found")
    return {"deleted": True}


@router.post("/reindex/{document_id}")
def reindex_document(document_id: str, req: ReindexRequest, db: Session = Depends(get_db)):
    result = index.reindex(db, document_id, req.content)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    return index.stats(db)
