from sqlalchemy.orm import Session

from knowledge_pipelines import clients
from knowledge_pipelines.erp_knowledge_engine import store, odoo_sync

# A genuine gap this module closes: Phase 9's own sync() (odoo_sync.py)
# has always been purely manually-triggered — nothing ever compared a
# freshly-fetched live schema against what was last stored to decide
# whether anything actually changed. Every sync re-ingested every table's
# prose into Vector Search unconditionally, real work performed whether
# or not the source schema had moved at all.
#
# This does NOT add a background daemon — this project has never had
# one, confirmed repeatedly across Phase 30's own dispatcher and Task
# Manager's dequeue() investigation. detect_drift()/check_and_sync() are
# real, explicit, callable-on-demand functions — a human, cron job, or
# external scheduler decides when to call them, same "poll-triggered,
# not continuously-running" posture already established for
# knowledge_pipelines' own document-watching feature
# (services/knowledge_pipelines/README.md, "What's a stub or simplified").


def _columns_by_name(table_info: dict) -> dict:
    return {c["name"]: c for c in table_info.get("columns", [])}


def _diff_table(old_info: dict, new_info: dict) -> dict | None:
    """Real column-level diff between two structured table schemas — not
    a prose comparison. Returns None if nothing about this table changed."""
    old_cols = _columns_by_name(old_info)
    new_cols = _columns_by_name(new_info)

    added = sorted(set(new_cols) - set(old_cols))
    removed = sorted(set(old_cols) - set(new_cols))
    changed = sorted(
        name for name in (set(old_cols) & set(new_cols))
        if old_cols[name].get("type") != new_cols[name].get("type")
    )

    if not (added or removed or changed):
        return None
    return {"added_columns": added, "removed_columns": removed, "changed_column_types": changed}


def detect_drift(db: Session, target_db: str, capability: str) -> dict:
    """
    Real, read-only comparison: fetches the live schema through the same
    authorized Database Connector path odoo_sync.sync() already uses
    (Phase 7's capability-gated introspection, no elevated privilege of
    its own), and diffs it — table-by-table, column-by-column — against
    the current stored snapshot's real structured `tables` JSON
    (ErpSchemaSnapshot.tables). Never writes anything; a pure check.
    """
    current = store.get_current_snapshot(db, target_db)
    if not current:
        return {
            "target_db": target_db, "drifted": True, "reason": "no prior snapshot exists",
            "added_tables": [], "removed_tables": [], "changed_tables": {},
        }

    live_schema = clients.fetch_schema(target_db, capability)
    live_tables = live_schema["tables"]
    old_tables = current.tables or {}

    added_tables = sorted(set(live_tables) - set(old_tables))
    removed_tables = sorted(set(old_tables) - set(live_tables))
    changed_tables = {}
    for name in set(live_tables) & set(old_tables):
        table_diff = _diff_table(old_tables[name], live_tables[name])
        if table_diff:
            changed_tables[name] = table_diff

    drifted = bool(added_tables or removed_tables or changed_tables)
    return {
        "target_db": target_db, "drifted": drifted,
        "compared_against_snapshot_id": current.id, "compared_against_synced_at": current.synced_at.isoformat(),
        "added_tables": added_tables, "removed_tables": removed_tables, "changed_tables": changed_tables,
    }


def check_and_sync(db: Session, target_db: str, capability: str, requested_by: str = "erp_knowledge_engine") -> dict:
    """
    The real "detect, then only act if warranted" call this whole module
    exists for: runs detect_drift() first, and calls the real,
    already-existing odoo_sync.sync() only when it found genuine drift —
    skipping the real re-ingestion work (a live schema fetch plus a
    Vector Search write per table) on every no-op check. Every call is
    still explicit — see the module docstring on why this is not a
    background daemon.
    """
    drift = detect_drift(db, target_db, capability)
    if not drift["drifted"]:
        return {"synced": False, "drift": drift}

    sync_result = odoo_sync.sync(db, target_db, capability, requested_by)
    return {"synced": True, "drift": drift, "sync_result": sync_result}
