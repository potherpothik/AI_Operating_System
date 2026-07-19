from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from knowledge_pipelines.db import get_db
from knowledge_pipelines import clients
from knowledge_pipelines.erp_knowledge_engine import store, odoo_sync, annotations, formulas, graph

router = APIRouter(prefix="/erp-knowledge", tags=["erp-knowledge"])


class SyncRequest(BaseModel):
    target_db: str
    capability: str = "database_agent"
    requested_by: str = "erp_knowledge_engine"


@router.post("/sync")
def sync(req: SyncRequest, db: Session = Depends(get_db)):
    try:
        result = odoo_sync.sync(db, req.target_db, req.capability, req.requested_by)
    except clients.SchemaFetchFailed as e:
        raise HTTPException(status_code=502, detail=f"schema sync failed, affected knowledge marked stale: {e}")
    return result


class AnnotateRequest(BaseModel):
    model_name: str
    field_name: str
    business_meaning: str
    annotated_by: str
    classification: str = "internal"


@router.post("/annotate")
def annotate(req: AnnotateRequest, db: Session = Depends(get_db)):
    return annotations.annotate(db, req.model_name, req.field_name, req.business_meaning, req.annotated_by, req.classification)


@router.get("/graph")
def get_graph(target_db: str, table: Optional[str] = None, direction: str = "full", db: Session = Depends(get_db)):
    """direction: 'full' (whole graph), 'references' (what `table` points
    to), or 'referenced_by' (what points at `table`) — the precise
    relational query mode the Phase 9 doc calls out as a distinct,
    more exact alternative to Vector Search's similarity search."""
    snapshot = store.get_current_snapshot(db, target_db)
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"no schema snapshot for {target_db!r} — call /erp-knowledge/sync first")
    if snapshot.status == "stale":
        raise HTTPException(status_code=409, detail=f"schema snapshot for {target_db!r} is stale — the last sync failed; re-sync before trusting this graph")

    if direction == "full":
        result = graph.full_graph(snapshot.tables)
    elif direction == "references":
        if not table:
            raise HTTPException(status_code=400, detail="table is required for direction=references")
        result = {"table": table, "references": graph.references_of(snapshot.tables, table)}
    elif direction == "referenced_by":
        if not table:
            raise HTTPException(status_code=400, detail="table is required for direction=referenced_by")
        result = {"table": table, "referenced_by": graph.tables_referencing(snapshot.tables, table)}
    else:
        raise HTTPException(status_code=400, detail=f"unknown direction {direction!r}")

    return {"snapshot_id": snapshot.id, "synced_at": snapshot.synced_at.isoformat(), **result}


class RegisterFormulaRequest(BaseModel):
    name: str
    formula_ref: str
    business_purpose: str
    defined_by: str
    target_namespace: str
    classification: Optional[str] = None


@router.post("/formula/register")
def register_formula(req: RegisterFormulaRequest, db: Session = Depends(get_db)):
    """
    Not in the Phase 9 doc's own API table (which lists only GET .../formula/{id}
    for retrieval) — a real, necessary gap: formulas.register_formula()
    needs an HTTP entry point for a human to actually register one.
    """
    return formulas.register_formula(db, req.name, req.formula_ref, req.business_purpose, req.defined_by, req.target_namespace, req.classification)


@router.get("/formula/{formula_id}")
def get_formula(formula_id: str, db: Session = Depends(get_db)):
    result = formulas.get_formula(db, formula_id)
    if not result:
        raise HTTPException(status_code=404, detail="formula not found")
    return result
