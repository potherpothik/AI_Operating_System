from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from knowledge_pipelines.db import get_db
from knowledge_pipelines import clients
from knowledge_pipelines.documentation_engine import parsers, classifier, watcher, store

router = APIRouter(prefix="/docs", tags=["documentation"])


def _source_out(source) -> dict:
    return {
        "id": source.id, "path_or_url": source.path_or_url, "source_type": source.source_type,
        "doc_type": source.doc_type, "project_id": source.project_id, "watch_enabled": source.watch_enabled,
        "document_id": source.document_id, "last_status": source.last_status,
        "last_ingested_at": source.last_ingested_at.isoformat() if source.last_ingested_at else None,
    }


class IngestRequest(BaseModel):
    path_or_url: str
    source_type: str = "file"
    doc_type: Optional[str] = None
    project_id: str
    explicit_classification: Optional[str] = None
    requested_by: str = "human_admin"
    watch: bool = False
    correlation_id: Optional[str] = None


@router.post("/ingest")
def ingest(req: IngestRequest, db: Session = Depends(get_db)):
    decision = clients.authorize(req.requested_by, "docs.ingest", req.project_id, correlation_id=req.correlation_id or "")
    if decision["decision"] != "allow":
        raise HTTPException(status_code=403, detail=decision.get("reason", "denied"))

    source = store.get_or_create_source(db, req.path_or_url, req.source_type, req.doc_type, req.project_id, watch_enabled=req.watch)

    try:
        parsed = parsers.parse(req.path_or_url, req.doc_type)
    except (parsers.UnsupportedFormat, parsers.ParseFailed) as e:
        # Unparseable documents surface as an explicit failure, never a
        # silent skip (Phase 9 doc, Documentation Engine failure handling).
        store.update_source_after_ingest(db, source, source.content_hash, source.document_id, "failed")
        store.log_ingestion(db, source.id, "failed", failure_reason=str(e))
        clients.audit_log(req.requested_by, "docs.ingest", req.path_or_url, decision="failed", reason=str(e), correlation_id=req.correlation_id or "")
        raise HTTPException(status_code=422, detail=str(e))

    classification, is_default = classifier.assign_classification(req.explicit_classification)
    doc_type = req.doc_type or parsed["structure_metadata"]["format"]

    vector_result = clients.vector_ingest(req.path_or_url, parsed["clean_text"], req.project_id, doc_type, classification)
    new_hash = watcher.content_hash(parsed["clean_text"])
    store.update_source_after_ingest(db, source, new_hash, vector_result["document_id"], "completed")
    store.log_ingestion(
        db, source.id, "completed", document_id=vector_result["document_id"],
        classification_assigned=classification, classification_is_default=is_default,
    )
    clients.audit_log(
        req.requested_by, "docs.ingest", req.path_or_url, decision="completed",
        reason=f"classification={classification} (default={is_default}), chunks={vector_result['chunks_created']}",
        correlation_id=req.correlation_id or "",
    )

    return {
        "source_id": source.id, "document_id": vector_result["document_id"], "status": "completed",
        "classification": classification, "classification_is_default": is_default,
        "chunks_created": vector_result["chunks_created"], "structure_metadata": parsed["structure_metadata"],
    }


class WatchRequest(BaseModel):
    path_or_url: str
    source_type: str = "file"
    doc_type: Optional[str] = None
    project_id: str


@router.post("/watch")
def watch(req: WatchRequest, db: Session = Depends(get_db)):
    source = store.get_or_create_source(db, req.path_or_url, req.source_type, req.doc_type, req.project_id, watch_enabled=True)
    source.watch_enabled = True
    db.commit()
    db.refresh(source)
    return _source_out(source)


@router.get("/sources")
def list_sources(project_id: Optional[str] = None, db: Session = Depends(get_db)):
    return {"sources": [_source_out(s) for s in store.list_sources(db, project_id=project_id)]}


@router.post("/sources/{source_id}/check")
def check_for_changes(source_id: str, db: Session = Depends(get_db)):
    """
    The actual "watch" mechanism: poll-triggered via this endpoint (a
    cron job or manual call), not a continuously-running background
    daemon — a deliberate, honest simplification. Compares the source's
    current content against its last-ingested hash and reindexes via
    Vector Search.reindex only if it genuinely changed, per the Phase 9
    doc's "triggers reindexing... rather than requiring manual
    re-ingestion."
    """
    source = store.get_source(db, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="source not found")
    if not source.watch_enabled:
        raise HTTPException(status_code=400, detail="watch is not enabled for this source")

    try:
        parsed = parsers.parse(source.path_or_url, source.doc_type)
    except (parsers.UnsupportedFormat, parsers.ParseFailed) as e:
        store.mark_stale(db, source.id)
        clients.audit_log("documentation_engine", "docs.check", source.path_or_url, decision="failed", reason=str(e))
        raise HTTPException(status_code=422, detail=str(e))

    if not watcher.has_changed(source.content_hash, parsed["clean_text"]):
        return {"changed": False, "source_id": source.id}

    if source.document_id:
        clients.vector_reindex(source.document_id, parsed["clean_text"])
    new_hash = watcher.content_hash(parsed["clean_text"])
    store.update_source_after_ingest(db, source, new_hash, source.document_id, "completed")
    clients.audit_log("documentation_engine", "docs.reindex", source.path_or_url, decision="completed")
    return {"changed": True, "source_id": source.id, "document_id": source.document_id}


class ClassifyOverrideRequest(BaseModel):
    source_id: str
    new_classification: str
    corrected_by: str
    correlation_id: Optional[str] = None


@router.post("/classify-override")
def classify_override(req: ClassifyOverrideRequest, db: Session = Depends(get_db)):
    """Human correction of an auto-assigned classification — always
    approval-gated, since it can only ever widen or narrow who can see
    real content (Phase 9 doc)."""
    source = store.get_source(db, req.source_id)
    if not source:
        raise HTTPException(status_code=404, detail="source not found")

    approval = clients.request_approval(
        action=f"docs.classify_override.{source.id}", requested_by=req.corrected_by,
        risk_tier="medium", payload_ref=f"{source.path_or_url} -> {req.new_classification}",
    )
    clients.audit_log(
        req.corrected_by, "docs.classify_override", source.path_or_url,
        decision="pending_approval", reason=f"proposed={req.new_classification}", correlation_id=req.correlation_id or "",
    )
    return {"status": "pending_approval", "approval_id": approval.get("id"), "source_id": source.id, "proposed_classification": req.new_classification}


@router.post("/classify-override/{approval_id}/confirm")
def confirm_classify_override(approval_id: str, source_id: str, new_classification: str, db: Session = Depends(get_db)):
    """
    Once approved, actually applies the correction. Vector Search (Phase
    3) has no in-place classification update, so this re-ingests under
    the new classification and retires the old document via its existing
    delete/ingest endpoints — no changes needed to Phase 3.
    """
    result = clients.get_approval_status(approval_id)
    if result.get("status") != "approved":
        return {"status": result.get("status", "unknown")}

    source = store.get_source(db, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="source not found")

    parsed = parsers.parse(source.path_or_url, source.doc_type)
    doc_type = source.doc_type or parsed["structure_metadata"]["format"]
    vector_result = clients.vector_ingest(source.path_or_url, parsed["clean_text"], source.project_id, doc_type, new_classification)

    old_document_id = source.document_id
    if old_document_id:
        clients.vector_delete(old_document_id)

    new_hash = watcher.content_hash(parsed["clean_text"])
    store.update_source_after_ingest(db, source, new_hash, vector_result["document_id"], "completed")
    store.log_ingestion(
        db, source.id, "completed", document_id=vector_result["document_id"],
        classification_assigned=new_classification, classification_is_default=False,
    )
    clients.audit_log("documentation_engine", "docs.classify_override.confirm", source.path_or_url, decision="applied", reason=new_classification)

    return {"status": "applied", "source_id": source.id, "document_id": vector_result["document_id"], "classification": new_classification}
