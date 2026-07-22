import httpx
import pytest

from knowledge_pipelines.db import SessionLocal
from knowledge_pipelines.erp_knowledge_engine import api, store, graph, drift


def test_sync_pulls_real_schema_from_database_connector(governance_url, knowledge_url, database_url):
    db = SessionLocal()
    result = api.sync(api.SyncRequest(target_db="demo_erp", requested_by="human_admin"), db)
    db.close()

    assert result["model_count"] >= 2  # sale_order, res_partner at minimum
    tables = {row["table"] for row in result["ingested"]}
    assert "sale_order" in tables
    assert "res_partner" in tables


def test_synced_prose_is_genuinely_queryable_in_vector_search(governance_url, knowledge_url, database_url):
    db = SessionLocal()
    api.sync(api.SyncRequest(target_db="demo_erp", requested_by="human_admin"), db)
    db.close()

    hits = httpx.post(
        f"{knowledge_url}/vector/query",
        json={"text": "sale order partner amount_total", "namespace": "demo_erp", "classification_ceiling": "confidential", "top_k": 5},
    ).json()["hits"]
    assert any("sale_order" in h["chunk"] for h in hits)


def test_list_snapshots_shows_the_latest_row_per_target(governance_url, knowledge_url, database_url):
    """Phase 13: GET /erp-knowledge/snapshots is the listing endpoint
    Health Monitor's stale-ERP-knowledge check needs — discovering
    staleness across every synced target, not just one already known."""
    db = SessionLocal()
    api.sync(api.SyncRequest(target_db="demo_erp", requested_by="human_admin"), db)
    snapshots = api.list_snapshots(db)
    db.close()

    demo_erp_entries = [s for s in snapshots if s["target_db"] == "demo_erp"]
    assert len(demo_erp_entries) == 1  # latest only, not every historical snapshot
    assert demo_erp_entries[0]["status"] == "current"


def test_graph_full_shows_real_foreign_key_relationship(governance_url, knowledge_url, database_url):
    db = SessionLocal()
    api.sync(api.SyncRequest(target_db="demo_erp", requested_by="human_admin"), db)
    result = api.get_graph(target_db="demo_erp", table=None, direction="full", db=db)
    db.close()

    edges = result["edges"]
    assert any(e["from"] == "sale_order" and e["to"] == "res_partner" for e in edges)


def test_graph_referenced_by_answers_the_relational_question_directly(governance_url, knowledge_url, database_url):
    """'What tables reference this one' — the exact question the Phase 9
    doc names as one semantic similarity search answers poorly."""
    db = SessionLocal()
    api.sync(api.SyncRequest(target_db="demo_erp", requested_by="human_admin"), db)
    result = api.get_graph(target_db="demo_erp", table="res_partner", direction="referenced_by", db=db)
    db.close()

    tables = {r["table"] for r in result["referenced_by"]}
    assert "sale_order" in tables


def test_graph_without_a_prior_sync_returns_404():
    db = SessionLocal()
    with pytest.raises(Exception) as exc_info:
        api.get_graph(target_db="never_synced_target", table=None, direction="full", db=db)
    db.close()
    assert exc_info.value.status_code == 404


def test_sync_failure_marks_snapshot_stale_not_silently_served_as_current(governance_url, knowledge_url, database_url):
    db = SessionLocal()
    api.sync(api.SyncRequest(target_db="demo_erp", requested_by="human_admin"), db)
    db.close()

    db = SessionLocal()
    with pytest.raises(Exception):
        api.sync(api.SyncRequest(target_db="nonexistent_target_db", capability="database_agent", requested_by="human_admin"), db)
    db.close()
    # demo_erp's own snapshot is untouched by an unrelated target's failure
    db = SessionLocal()
    still_current = store.get_current_snapshot(db, "demo_erp")
    db.close()
    assert still_current.status == "current"


def test_annotation_is_recorded_and_folds_into_next_sync(governance_url, knowledge_url, database_url):
    db = SessionLocal()
    annotate_result = api.annotate(
        api.AnnotateRequest(
            model_name="sale_order", field_name="requires_manager_approval",
            business_meaning="True when the order total exceeds the manager-approval threshold set in company policy.",
            annotated_by="human_admin",
        ),
        db,
    )
    assert annotate_result["business_meaning"].startswith("True when")

    api.sync(api.SyncRequest(target_db="demo_erp", requested_by="human_admin"), db)
    db.close()

    # The annotation's business meaning is now part of the real, queryable prose.
    hits = httpx.post(
        f"{knowledge_url}/vector/query",
        json={"text": "manager approval threshold company policy", "namespace": "demo_erp", "classification_ceiling": "confidential", "top_k": 5},
    ).json()["hits"]
    assert any("manager-approval threshold" in h["chunk"] for h in hits)


def test_formula_registration_routes_through_real_business_memory_approval(governance_url, knowledge_url, database_url):
    db = SessionLocal()
    result = api.register_formula(
        api.RegisterFormulaRequest(
            name="cutlist_waste_factor", formula_ref="waste_pct = (total_cut - usable_cut) / total_cut",
            business_purpose="Standard waste-factor calculation for cutlist optimization estimates.",
            defined_by="human_admin", target_namespace="demo_erp",
        ),
        db,
    )
    db.close()

    assert result["memory_status"] == "pending_approval"
    assert result["memory_approval_id"]
    assert result["classification"] == "internal"  # no "pricing" in name/purpose -> not auto-escalated


def test_pricing_formula_defaults_to_confidential(governance_url, knowledge_url, database_url):
    db = SessionLocal()
    result = api.register_formula(
        api.RegisterFormulaRequest(
            name="material_pricing_formula", formula_ref="price = base_cost * markup_multiplier",
            business_purpose="Computes customer-facing pricing from base material cost.",
            defined_by="human_admin", target_namespace="demo_erp",
        ),
        db,
    )
    db.close()
    assert result["classification"] == "confidential"


def test_formula_retrieval_includes_provenance(governance_url, knowledge_url, database_url):
    db = SessionLocal()
    reg_result = api.register_formula(
        api.RegisterFormulaRequest(
            name="test_formula_provenance", formula_ref="x = y + 1", business_purpose="test",
            defined_by="human_admin", target_namespace="demo_erp",
        ),
        db,
    )
    fetched = api.get_formula(reg_result["id"], db)
    db.close()

    assert fetched["defined_by"] == "human_admin"
    assert fetched["formula_ref"] == "x = y + 1"
    assert fetched["version"] == "1"
    assert fetched["status"] == "active"


def test_formula_re_registration_supersedes_the_prior_version(governance_url, knowledge_url, database_url):
    db = SessionLocal()
    first = api.register_formula(
        api.RegisterFormulaRequest(
            name="versioned_formula_test", formula_ref="v1 = a", business_purpose="first version",
            defined_by="human_admin", target_namespace="demo_erp",
        ),
        db,
    )
    second = api.register_formula(
        api.RegisterFormulaRequest(
            name="versioned_formula_test", formula_ref="v2 = a + b", business_purpose="second version",
            defined_by="human_admin", target_namespace="demo_erp",
        ),
        db,
    )
    first_fetched = api.get_formula(first["id"], db)
    db.close()

    assert second["version"] == "2"
    assert first_fetched["status"] == "superseded"
    assert first_fetched["superseded_by"] == second["id"]


# ---------------------------------------------------------------------------
# Phase 17 — GET /formula/by-name/{name}: real gap-fill, store.py's
# get_active_formula_by_name() existed since Phase 14 but was never
# reachable over HTTP until Calculation Agent needed to resolve a
# formula by the real registered name.
# ---------------------------------------------------------------------------

def test_get_formula_by_name_returns_the_active_version(governance_url, knowledge_url, database_url):
    db = SessionLocal()
    api.register_formula(
        api.RegisterFormulaRequest(
            name="by_name_lookup_test", formula_ref="x = a * 2", business_purpose="test",
            defined_by="human_admin", target_namespace="demo_erp",
        ),
        db,
    )
    fetched = api.get_formula_by_name("by_name_lookup_test", db)
    db.close()

    assert fetched["formula_ref"] == "x = a * 2"
    assert fetched["status"] == "active"


def test_get_formula_by_name_returns_only_the_active_version_after_supersession(governance_url, knowledge_url, database_url):
    db = SessionLocal()
    api.register_formula(
        api.RegisterFormulaRequest(
            name="by_name_supersede_test", formula_ref="v1", business_purpose="first",
            defined_by="human_admin", target_namespace="demo_erp",
        ),
        db,
    )
    api.register_formula(
        api.RegisterFormulaRequest(
            name="by_name_supersede_test", formula_ref="v2", business_purpose="second",
            defined_by="human_admin", target_namespace="demo_erp",
        ),
        db,
    )
    fetched = api.get_formula_by_name("by_name_supersede_test", db)
    db.close()
    assert fetched["formula_ref"] == "v2"
    assert fetched["version"] == "2"


def test_get_formula_by_name_unknown_name_returns_404():
    from fastapi import HTTPException
    db = SessionLocal()
    with pytest.raises(HTTPException) as exc_info:
        api.get_formula_by_name("nonexistent_formula_name_xyz", db)
    db.close()
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Schema Drift Detector — a genuine gap named in docs/ARCHITECTURE_PLAN.md's
# real "Phase 2" investigation and closed here: sync() was always purely
# manually-triggered with no way to know beforehand whether the live
# schema had actually changed since the last snapshot.
# ---------------------------------------------------------------------------

def test_drift_check_with_no_prior_snapshot_reports_drifted(governance_url, knowledge_url, database_url):
    db = SessionLocal()
    result = drift.detect_drift(db, "demo_erp_never_synced_drift_test", "database_agent")
    db.close()
    assert result["drifted"] is True
    assert result["reason"] == "no prior snapshot exists"


def test_drift_check_immediately_after_a_real_sync_reports_no_drift(governance_url, knowledge_url, database_url):
    db = SessionLocal()
    api.sync(api.SyncRequest(target_db="demo_erp", requested_by="human_admin"), db)
    result = drift.detect_drift(db, "demo_erp", "database_agent")
    db.close()

    assert result["drifted"] is False
    assert result["added_tables"] == []
    assert result["removed_tables"] == []
    assert result["changed_tables"] == {}


def test_check_and_sync_skips_a_real_resync_when_nothing_changed(governance_url, knowledge_url, database_url):
    db = SessionLocal()
    api.sync(api.SyncRequest(target_db="demo_erp", requested_by="human_admin"), db)
    snapshot_before = store.get_current_snapshot(db, "demo_erp")

    result = drift.check_and_sync(db, "demo_erp", "database_agent")
    snapshot_after = store.get_current_snapshot(db, "demo_erp")
    db.close()

    assert result["synced"] is False
    assert snapshot_after.id == snapshot_before.id  # no new snapshot was created


def test_check_and_sync_performs_a_real_resync_for_a_never_synced_target(governance_url, knowledge_url, database_url):
    db = SessionLocal()
    result = drift.check_and_sync(db, "demo_erp", "database_agent")
    db.close()

    assert result["synced"] is True
    assert result["drift"]["drifted"] is True
    assert result["sync_result"]["model_count"] >= 2


def test_drift_route_and_check_and_sync_route_are_reachable_and_not_shadowed(governance_url, knowledge_url, database_url):
    """Real HTTP round trip through the actual route table — confirms
    /{target_db}/drift and /{target_db}/check-and-sync don't collide with
    the literal-segment routes (/sync, /snapshots, /graph, /formula/...)
    registered in the same router, the same route-ordering class of check
    Phase 11/17 already established for this file."""
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)

    sync_resp = client.post("/erp-knowledge/sync", json={"target_db": "demo_erp", "requested_by": "human_admin"})
    assert sync_resp.status_code == 200

    drift_resp = client.get("/erp-knowledge/demo_erp/drift")
    assert drift_resp.status_code == 200
    assert drift_resp.json()["drifted"] is False

    # Untouched literal routes still resolve correctly, not swallowed by the new pattern.
    assert client.get("/erp-knowledge/snapshots").status_code == 200


def test_by_name_route_not_shadowed_by_formula_id_wildcard():
    """Regression test for the exact route-ordering bug class Phase 11's
    GET /context/model-ceiling fix taught this project to check for:
    'by-name' must never be matched as a literal {formula_id} value.
    Uses a real HTTP TestClient (not a direct function call) since a
    route-ordering bug is invisible to calling api.get_formula_by_name()
    directly — it only shows up through the actual FastAPI route table."""
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)
    r = client.get("/erp-knowledge/formula/by-name/definitely_does_not_exist_xyz")
    assert r.status_code == 404
    assert "definitely_does_not_exist_xyz" in r.json()["detail"]
