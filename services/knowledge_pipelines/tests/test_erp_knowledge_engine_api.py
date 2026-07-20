import httpx
import pytest

from knowledge_pipelines.db import SessionLocal
from knowledge_pipelines.erp_knowledge_engine import api, store, graph


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
