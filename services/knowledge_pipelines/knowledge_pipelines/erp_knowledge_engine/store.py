import datetime
from sqlalchemy.orm import Session

from knowledge_pipelines.erp_knowledge_engine.models import ErpSchemaSnapshot, ErpFieldAnnotation, ErpFormula


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def create_snapshot(db: Session, target_db: str, tables: dict) -> ErpSchemaSnapshot:
    # A new current snapshot supersedes any prior one for the same target.
    db.query(ErpSchemaSnapshot).filter(ErpSchemaSnapshot.target_db == target_db, ErpSchemaSnapshot.status == "current").update({"status": "stale"})
    snapshot = ErpSchemaSnapshot(target_db=target_db, model_count=len(tables), tables=tables, status="current")
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def get_current_snapshot(db: Session, target_db: str) -> ErpSchemaSnapshot | None:
    return (
        db.query(ErpSchemaSnapshot)
        .filter(ErpSchemaSnapshot.target_db == target_db, ErpSchemaSnapshot.status == "current")
        .order_by(ErpSchemaSnapshot.synced_at.desc())
        .first()
    )


def mark_snapshot_stale(db: Session, target_db: str):
    db.query(ErpSchemaSnapshot).filter(ErpSchemaSnapshot.target_db == target_db, ErpSchemaSnapshot.status == "current").update({"status": "stale"})
    db.commit()


def list_latest_snapshots(db: Session) -> list[ErpSchemaSnapshot]:
    """
    Phase 13: Health Monitor's stale-ERP-knowledge check needs to see
    every `target_db` that has ever been synced, not just one you
    already know to ask `get_current_snapshot` about — the whole point
    is discovering staleness you didn't already know to look for. One
    row per target_db: its most recent snapshot, whatever status that
    happens to be (a target with no successful sync since a failure has
    no "current" row at all, only a "stale" one — that's still the
    latest and still the answer this needs).
    """
    all_rows = db.query(ErpSchemaSnapshot).order_by(ErpSchemaSnapshot.synced_at.desc()).all()
    latest_by_target = {}
    for row in all_rows:
        if row.target_db not in latest_by_target:
            latest_by_target[row.target_db] = row
    return list(latest_by_target.values())


def add_annotation(db: Session, model_name: str, field_name: str, business_meaning: str, annotated_by: str, classification: str = "internal") -> ErpFieldAnnotation:
    row = ErpFieldAnnotation(
        model_name=model_name, field_name=field_name, business_meaning=business_meaning,
        annotated_by=annotated_by, classification=classification,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_annotations_for_model(db: Session, model_name: str) -> list[ErpFieldAnnotation]:
    return db.query(ErpFieldAnnotation).filter(ErpFieldAnnotation.model_name == model_name).all()


def create_formula(db: Session, name: str, formula_ref: str, business_purpose: str, classification: str, defined_by: str, version: str = "1") -> ErpFormula:
    row = ErpFormula(name=name, formula_ref=formula_ref, business_purpose=business_purpose, classification=classification, defined_by=defined_by, version=version)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_formula(db: Session, formula_id: str) -> ErpFormula | None:
    return db.query(ErpFormula).filter(ErpFormula.id == formula_id).first()


def get_active_formula_by_name(db: Session, name: str) -> ErpFormula | None:
    return db.query(ErpFormula).filter(ErpFormula.name == name, ErpFormula.status == "active").order_by(ErpFormula.version.desc()).first()


def supersede_formula(db: Session, old_formula_id: str, new_formula: ErpFormula):
    old = db.query(ErpFormula).filter(ErpFormula.id == old_formula_id).first()
    if old:
        old.status = "superseded"
        old.superseded_by = new_formula.id
        db.commit()
