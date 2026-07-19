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
