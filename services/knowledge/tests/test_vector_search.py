from knowledge.db import SessionLocal
from knowledge.vector_search import index
from knowledge.vector_search.chunking import chunk_text


def test_chunking_respects_word_limit_with_overlap():
    text = " ".join(f"word{i}" for i in range(500))
    chunks = chunk_text(text, max_words=200, overlap_words=30)
    assert len(chunks) > 1
    for c in chunks[:-1]:
        assert len(c.split()) == 200


def test_short_text_is_a_single_chunk():
    chunks = chunk_text("just a short sentence", max_words=200)
    assert len(chunks) == 1


def test_ingest_and_query_returns_relevant_chunk():
    db = SessionLocal()
    index.ingest(
        db,
        source="odoo-docs/sale-order.md",
        content="The sale.order model tracks the lifecycle of a customer order from quotation to invoice.",
        project_id="proj-1",
    )
    index.ingest(
        db,
        source="manufacturing-docs/cutlist.md",
        content="Cutlist optimization solves a bin packing problem to minimize panel waste.",
        project_id="proj-1",
    )

    hits = index.query(db, "what does the sale order model track", namespace="proj-1", top_k=1)
    assert len(hits) == 1
    assert "sale.order" in hits[0]["chunk"]
    db.close()


def test_classification_ceiling_filters_results_server_side():
    db = SessionLocal()
    index.ingest(db, source="public-doc", content="general company information for anyone", project_id="proj-2", classification="public")
    index.ingest(db, source="secret-doc", content="confidential pricing formula details here", project_id="proj-2", classification="confidential")

    low_ceiling_hits = index.query(db, "pricing formula", namespace="proj-2", classification_ceiling="internal", top_k=5)
    assert all(h["classification"] != "confidential" for h in low_ceiling_hits)

    high_ceiling_hits = index.query(db, "pricing formula", namespace="proj-2", classification_ceiling="confidential", top_k=5)
    assert any(h["classification"] == "confidential" for h in high_ceiling_hits)
    db.close()


def test_namespace_isolation():
    db = SessionLocal()
    index.ingest(db, source="a", content="alpha project unique content marker zzyx", project_id="proj-alpha")
    index.ingest(db, source="b", content="beta project unique content marker zzyx", project_id="proj-beta")

    alpha_hits = index.query(db, "zzyx", namespace="proj-alpha", top_k=5)
    assert all("alpha" in h["chunk"] for h in alpha_hits)
    db.close()


def test_delete_document_removes_its_chunks():
    db = SessionLocal()
    result = index.ingest(db, source="temp-doc", content="content to be deleted soon", project_id="proj-3")
    doc_id = result["document_id"]

    assert index.delete_document(db, doc_id) is True
    assert index.delete_document(db, doc_id) is False  # already gone

    hits = index.query(db, "deleted soon", namespace="proj-3", top_k=5)
    assert len(hits) == 0
    db.close()


def test_reindex_replaces_chunks_and_bumps_version():
    db = SessionLocal()
    result = index.ingest(db, source="evolving-doc", content="original content version one", project_id="proj-4")
    doc_id = result["document_id"]

    reindexed = index.reindex(db, doc_id, "completely different replacement content")
    assert reindexed["version"] == "2"

    hits = index.query(db, "replacement content", namespace="proj-4", top_k=5)
    assert any("replacement" in h["chunk"] for h in hits)
    old_hits = index.query(db, "original content version one", namespace="proj-4", top_k=5)
    assert not any("original content" in h["chunk"] for h in old_hits)
    db.close()


def test_stats_reports_counts_by_project():
    db = SessionLocal()
    index.ingest(db, source="a", content="some content here", project_id="proj-stats")
    result = index.stats(db)
    assert result["documents"] >= 1
    assert "proj-stats" in result["by_project"]
    db.close()


def test_stats_reports_counts_by_classification():
    """Phase 13: Metrics Dashboard's classification-distribution category."""
    db = SessionLocal()
    index.ingest(db, source="b", content="confidential content here", project_id="proj-stats-2", classification="confidential")
    result = index.stats(db)
    assert result["by_classification"].get("confidential", 0) >= 1
    db.close()
