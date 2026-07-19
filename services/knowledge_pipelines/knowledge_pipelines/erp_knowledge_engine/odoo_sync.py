from sqlalchemy.orm import Session

from knowledge_pipelines import clients
from knowledge_pipelines.erp_knowledge_engine import store


def _table_prose(table_name: str, table_info: dict, annotations: dict) -> str:
    """
    Chunked prose for Vector Search's semantic retrieval — a plain-
    language description a similarity search can actually match against,
    not raw JSON schema dumped as text (Phase 9 doc: "Produces both
    chunked-prose knowledge for semantic retrieval and a structured
    relationship graph").
    """
    columns = table_info.get("columns", [])
    column_descriptions = []
    for col in columns:
        meaning = annotations.get(col["name"])
        if meaning:
            column_descriptions.append(f"{col['name']} ({col['type']}): {meaning}")
        else:
            column_descriptions.append(f"{col['name']} ({col['type']})")

    lines = [f"Table {table_name} has columns: {', '.join(column_descriptions)}."]
    for fk in table_info.get("foreign_keys", []):
        lines.append(f"{table_name} references {fk['references_table']} via {', '.join(fk['columns'])}.")
    return " ".join(lines)


def sync(db: Session, target_db: str, capability: str, requested_by: str = "erp_knowledge_engine") -> dict:
    """
    Live re-sync against Database Connector's read-only schema
    introspection (Phase 7) — the same authorized, capability-gated path
    any other read goes through; ERP Knowledge Engine holds no elevated
    DB privilege of its own (Phase 9 doc, Security).
    """
    try:
        schema = clients.fetch_schema(target_db, capability)
    except clients.SchemaFetchFailed as e:
        # A failed sync marks affected knowledge stale rather than
        # continuing to serve it as current (Phase 9 doc, ERP Knowledge
        # Engine failure handling — inherited from Phase 7's fail-closed
        # schema-read discipline).
        store.mark_snapshot_stale(db, target_db)
        clients.audit_log(requested_by, "erp.sync", target_db, decision="failed", reason=str(e))
        raise

    tables = schema["tables"]
    snapshot = store.create_snapshot(db, target_db, tables)

    ingested = []
    for table_name, table_info in tables.items():
        annotations = {a.field_name: a.business_meaning for a in store.get_annotations_for_model(db, table_name)}
        prose = _table_prose(table_name, table_info, annotations)
        result = clients.vector_ingest(
            source=f"erp_schema:{target_db}:{table_name}", content=prose, project_id=target_db,
            doc_type="erp_schema", classification="internal",
        )
        ingested.append({"table": table_name, "document_id": result["document_id"]})

    clients.audit_log(requested_by, "erp.sync", target_db, decision="completed", reason=f"tables={len(tables)}")
    return {
        "snapshot_id": snapshot.id, "target_db": target_db, "model_count": snapshot.model_count,
        "synced_at": snapshot.synced_at.isoformat(), "ingested": ingested,
    }
