from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from knowledge_pipelines.db import get_db
from knowledge_pipelines import clients
from knowledge_pipelines.erp_knowledge_engine import store, odoo_sync, annotations, formulas, graph, drift

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


@router.get("/{target_db}/drift")
def check_drift(target_db: str, capability: str = "database_agent", db: Session = Depends(get_db)):
    """
    Real, read-only schema-drift check — a genuine gap this closes:
    every prior sync was purely manually-triggered with no way to know
    beforehand whether anything had actually changed. Compares the live
    schema against the current stored snapshot table-by-table,
    column-by-column; never writes anything.
    """
    try:
        return drift.detect_drift(db, target_db, capability)
    except clients.SchemaFetchFailed as e:
        raise HTTPException(status_code=502, detail=f"could not fetch live schema to check drift: {e}")


@router.post("/{target_db}/check-and-sync")
def check_and_sync(target_db: str, capability: str = "database_agent", requested_by: str = "erp_knowledge_engine", db: Session = Depends(get_db)):
    """
    Detects drift first, and only performs the real re-sync (a live
    schema fetch plus a Vector Search write per table) when something
    genuinely changed — an explicit, on-demand call (cron, a human, an
    external scheduler), never a background daemon this project has
    never had anywhere.
    """
    try:
        return drift.check_and_sync(db, target_db, capability, requested_by)
    except clients.SchemaFetchFailed as e:
        raise HTTPException(status_code=502, detail=f"schema check failed: {e}")


class AnnotateRequest(BaseModel):
    model_name: str
    field_name: str
    business_meaning: str
    annotated_by: str
    classification: str = "internal"


@router.post("/annotate")
def annotate(req: AnnotateRequest, db: Session = Depends(get_db)):
    return annotations.annotate(db, req.model_name, req.field_name, req.business_meaning, req.annotated_by, req.classification)


@router.get("/snapshots")
def list_snapshots(db: Session = Depends(get_db)):
    """
    Phase 13: one row per `target_db` ever synced, whatever its latest
    status is — Health Monitor's stale-ERP-knowledge gap check needs
    this to discover staleness across every target, not just the one it
    already knows to ask `GET /graph?target_db=...` about.
    """
    snapshots = store.list_latest_snapshots(db)
    return [
        {"id": s.id, "target_db": s.target_db, "status": s.status, "model_count": s.model_count, "synced_at": s.synced_at.isoformat()}
        for s in snapshots
    ]


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


@router.get("/formula/by-name/{name}")
def get_formula_by_name(name: str, db: Session = Depends(get_db)):
    """
    Phase 17: registered BEFORE the /{formula_id} route below — a
    literal path segment ("by-name") would otherwise be swallowed by
    the {formula_id} path parameter and matched as if it were an id,
    the exact route-ordering class of bug Phase 11's own
    GET /context/model-ceiling fix (services/assembly) taught this
    project to check for on every new literal-path route since.
    """
    result = formulas.get_active_formula_by_name(db, name)
    if not result:
        raise HTTPException(status_code=404, detail=f"no active formula named {name!r}")
    return result


@router.get("/formula/{formula_id}")
def get_formula(formula_id: str, db: Session = Depends(get_db)):
    result = formulas.get_formula(db, formula_id)
    if not result:
        raise HTTPException(status_code=404, detail="formula not found")
    return result
