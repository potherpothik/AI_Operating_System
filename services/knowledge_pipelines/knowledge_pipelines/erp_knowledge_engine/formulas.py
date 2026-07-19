import json
from sqlalchemy.orm import Session

from knowledge_pipelines import clients
from knowledge_pipelines.erp_knowledge_engine import store


def default_classification(name: str, business_purpose: str) -> str:
    """
    Engineering/costing formulas default to at least "internal",
    "confidential" for pricing specifically, unless a human explicitly
    marks otherwise (Phase 9 doc, ERP Knowledge Engine Security) — this
    is the default-assignment heuristic that fires only when the caller
    didn't provide an explicit classification, mirroring Documentation
    Engine's own classifier.py posture of resolving ambiguity toward the
    more restrictive tier.
    """
    text = f"{name} {business_purpose}".lower()
    if "pricing" in text or "price" in text:
        return "confidential"
    return "internal"


def register_formula(db: Session, name: str, formula_ref: str, business_purpose: str, defined_by: str,
                      target_namespace: str, classification: str = None) -> dict:
    """
    A formula is exactly the "durable, versioned business rule" the
    Phase 9 doc routes to Memory Manager's business_memory — which, per
    Phase 3's retention policy, requires real Human Approval Layer
    sign-off to write. Never LLM-drafted (explicit out-of-scope note) —
    always a human-authored registration.
    """
    resolved_classification = classification or default_classification(name, business_purpose)

    existing = store.get_active_formula_by_name(db, name)
    next_version = str(int(existing.version) + 1) if existing and existing.version.isdigit() else "1"

    value = json.dumps({"formula_ref": formula_ref, "business_purpose": business_purpose, "version": next_version})
    memory_result = clients.memory_write(
        "business_memory", target_namespace, name, value, defined_by, classification_hint=resolved_classification,
    )

    row = store.create_formula(db, name, formula_ref, business_purpose, resolved_classification, defined_by, version=next_version)
    if existing:
        store.supersede_formula(db, existing.id, row)

    clients.audit_log(
        defined_by, "erp.formula.register", name, decision=memory_result.get("status", "recorded"),
        reason=f"classification={resolved_classification}, version={next_version}",
    )

    return {
        "id": row.id, "name": row.name, "version": row.version, "classification": resolved_classification,
        "memory_status": memory_result.get("status"), "memory_approval_id": memory_result.get("approval_id"),
    }


def get_formula(db: Session, formula_id: str) -> dict | None:
    row = store.get_formula(db, formula_id)
    if not row:
        return None
    return {
        "id": row.id, "name": row.name, "formula_ref": row.formula_ref, "business_purpose": row.business_purpose,
        "classification": row.classification, "defined_by": row.defined_by, "version": row.version,
        "status": row.status, "superseded_by": row.superseded_by, "created_at": row.created_at.isoformat(),
    }
