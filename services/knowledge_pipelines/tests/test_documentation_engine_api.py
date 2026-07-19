import httpx
import pytest

from knowledge_pipelines.db import SessionLocal
from knowledge_pipelines.documentation_engine import api


def test_ingest_real_markdown_lands_in_vector_search(governance_url, knowledge_url, tmp_path):
    f = tmp_path / "policy.md"
    f.write_text("# Invoice Policy\n\nInvoices over $5000 require manager approval.\n")

    db = SessionLocal()
    result = api.ingest(
        api.IngestRequest(path_or_url=str(f), project_id="docs-test-1", requested_by="human_admin"),
        db,
    )
    db.close()

    assert result["status"] == "completed"
    assert result["chunks_created"] >= 1
    assert result["classification"] == "confidential"  # no explicit classification given -> most restrictive default
    assert result["classification_is_default"] is True

    # Independent verification: query Vector Search directly for the real content.
    hits = httpx.post(
        f"{knowledge_url}/vector/query",
        json={"text": "invoice manager approval", "namespace": "docs-test-1", "classification_ceiling": "confidential", "top_k": 5},
    ).json()["hits"]
    assert any("manager approval" in h["chunk"] for h in hits)


def test_ingest_honors_explicit_classification(governance_url, knowledge_url, tmp_path):
    f = tmp_path / "public_notice.md"
    f.write_text("# Public Notice\n\nOffice closed on holidays.\n")

    db = SessionLocal()
    result = api.ingest(
        api.IngestRequest(path_or_url=str(f), project_id="docs-test-2", requested_by="human_admin", explicit_classification="public"),
        db,
    )
    db.close()
    assert result["classification"] == "public"
    assert result["classification_is_default"] is False


def test_ingest_unparseable_document_fails_explicitly_not_silently(governance_url, knowledge_url, tmp_path):
    f = tmp_path / "broken.pdf"
    f.write_bytes(b"not a real pdf")

    db = SessionLocal()
    with pytest.raises(Exception) as exc_info:
        api.ingest(api.IngestRequest(path_or_url=str(f), project_id="docs-test-3", requested_by="human_admin"), db)
    db.close()
    assert exc_info.value.status_code == 422

    # And the failure is recorded, not silently dropped.
    db = SessionLocal()
    sources = store_all(db, "docs-test-3")
    db.close()
    assert sources[0].last_status == "failed"


def store_all(db, project_id):
    from knowledge_pipelines.documentation_engine import store
    return store.list_sources(db, project_id=project_id)


def test_watch_and_check_detects_real_content_change_and_reindexes(governance_url, knowledge_url, tmp_path):
    f = tmp_path / "watched.md"
    f.write_text("# Version 1\n\nOriginal content.\n")

    db = SessionLocal()
    ingest_result = api.ingest(api.IngestRequest(path_or_url=str(f), project_id="docs-test-4", requested_by="human_admin", watch=True), db)
    db.close()

    # No change yet — check should report changed=False.
    db = SessionLocal()
    unchanged_result = api.check_for_changes(ingest_result["source_id"], db)
    db.close()
    assert unchanged_result["changed"] is False

    # Genuinely modify the file on disk.
    f.write_text("# Version 2\n\nCompletely different content about refund policy.\n")
    db = SessionLocal()
    changed_result = api.check_for_changes(ingest_result["source_id"], db)
    db.close()
    assert changed_result["changed"] is True

    # Independent verification: the real reindexed content is now queryable.
    hits = httpx.post(
        f"{knowledge_url}/vector/query",
        json={"text": "refund policy", "namespace": "docs-test-4", "classification_ceiling": "confidential", "top_k": 5},
    ).json()["hits"]
    assert any("refund policy" in h["chunk"] for h in hits)


def test_check_for_changes_requires_watch_enabled(governance_url, knowledge_url, tmp_path):
    f = tmp_path / "not_watched.md"
    f.write_text("# Not Watched\n\nContent.\n")

    db = SessionLocal()
    result = api.ingest(api.IngestRequest(path_or_url=str(f), project_id="docs-test-5", requested_by="human_admin", watch=False), db)
    with pytest.raises(Exception) as exc_info:
        api.check_for_changes(result["source_id"], db)
    db.close()
    assert exc_info.value.status_code == 400


def test_classify_override_requires_real_approval_before_applying(governance_url, knowledge_url, tmp_path):
    f = tmp_path / "sensitive.md"
    f.write_text("# Draft\n\nSome content that was auto-classified.\n")

    db = SessionLocal()
    ingest_result = api.ingest(api.IngestRequest(path_or_url=str(f), project_id="docs-test-6", requested_by="human_admin"), db)
    original_document_id = ingest_result["document_id"]

    override_result = api.classify_override(
        api.ClassifyOverrideRequest(source_id=ingest_result["source_id"], new_classification="public", corrected_by="human_admin"),
        db,
    )
    db.close()
    assert override_result["status"] == "pending_approval"

    # Not applied yet.
    db = SessionLocal()
    from knowledge_pipelines.documentation_engine import store
    still_pending_source = store.get_source(db, ingest_result["source_id"])
    db.close()
    assert still_pending_source.document_id == original_document_id

    # Approve for real, then confirm.
    httpx.post(f"{governance_url}/approval/{override_result['approval_id']}/decide", json={"decided_by": "human_admin", "approve": True})
    db = SessionLocal()
    confirm_result = api.confirm_classify_override(override_result["approval_id"], ingest_result["source_id"], "public", db)
    db.close()

    assert confirm_result["status"] == "applied"
    assert confirm_result["classification"] == "public"
    assert confirm_result["document_id"] != original_document_id  # a real new document, old one retired

    # The old document is genuinely deleted, not just orphaned — attempting
    # to reindex it now hits Vector Search's real 404, not an assumption.
    reindex_old = httpx.post(f"{knowledge_url}/vector/reindex/{original_document_id}", json={"content": "x"})
    assert reindex_old.status_code == 404
