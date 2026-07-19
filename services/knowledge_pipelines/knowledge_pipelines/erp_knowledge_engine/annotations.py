from sqlalchemy.orm import Session

from knowledge_pipelines import clients
from knowledge_pipelines.erp_knowledge_engine import store


def annotate(db: Session, model_name: str, field_name: str, business_meaning: str, annotated_by: str, classification: str = "internal") -> dict:
    """
    A human adds business context to a schema element — raw introspection
    tells an agent a column's name, never its meaning (Phase 9 doc,
    trade-offs: "encoding tribal knowledge always needs a human source
    somewhere"). No automatic annotation generation — this is always a
    human-authored write, never LLM-drafted (explicit out-of-scope note).
    Durable storage only; the NEXT odoo_sync.sync() call is what folds
    this into the table's re-generated prose for Vector Search, keeping
    "record business knowledge" and "produce retrievable content"
    cleanly separate responsibilities.
    """
    row = store.add_annotation(db, model_name, field_name, business_meaning, annotated_by, classification)
    clients.audit_log(
        annotated_by, "erp.annotate", f"{model_name}.{field_name}",
        decision="recorded", reason=business_meaning[:200],
    )
    return {
        "id": row.id, "model_name": row.model_name, "field_name": row.field_name,
        "business_meaning": row.business_meaning, "classification": row.classification,
        "annotated_by": row.annotated_by, "annotated_at": row.annotated_at.isoformat(),
    }
