from datetime import datetime, timezone, timedelta

from knowledge.db import SessionLocal
from knowledge.memory_manager import store
from knowledge.memory_manager.models import MemoryRecord


def test_write_and_read_round_trip():
    db = SessionLocal()
    record, outcome = store.write(db, "project_memory", "proj-1", "onboarding-notes", "some notes", actor="human_admin")
    assert outcome["status"] == "active"

    fetched = store.read(db, "project_memory", "proj-1", "onboarding-notes")
    assert fetched.value == "some notes"
    db.close()


def test_unknown_memory_type_raises():
    db = SessionLocal()
    try:
        store.write(db, "not_a_real_type", "ns", "k", "v", actor="x")
        assert False, "should have raised"
    except ValueError:
        pass
    db.close()


def test_versioned_write_supersedes_prior_record():
    db = SessionLocal()
    r1, _ = store.write(db, "long_term", "proj-1", "fact-x", "version 1", actor="human_admin")
    r2, _ = store.write(db, "long_term", "proj-1", "fact-x", "version 2", actor="human_admin")

    db.refresh(r1)
    assert r1.superseded_by == r2.id

    current = store.read(db, "long_term", "proj-1", "fact-x")
    assert current.value == "version 2"
    db.close()


def test_decision_history_is_never_deletable():
    db = SessionLocal()
    record, _ = store.write(db, "decision_history", "proj-1", "adr-1", "we chose X because Y", actor="human_admin")
    ok, reason = store.delete(db, "decision_history", record.id)
    assert ok is False
    assert "not deletable" in reason
    db.close()


def test_user_preferences_are_deletable():
    db = SessionLocal()
    record, _ = store.write(db, "user_preferences", "global", "verbosity", "concise", actor="alice")
    ok, reason = store.delete(db, "user_preferences", record.id)
    assert ok is True
    assert store.read(db, "user_preferences", "global", "verbosity") is None
    db.close()


def test_classification_ceiling_enforced_at_read_time():
    db = SessionLocal()
    record, _ = store.write(
        db, "project_memory", "proj-1", "sensitive-note", "api_key: sk-abcdef123456", actor="human_admin"
    )
    assert record.classification == "confidential"  # heuristic should have caught this

    visible_to_low_ceiling = store.read(db, "project_memory", "proj-1", "sensitive-note", requester_ceiling="internal")
    assert visible_to_low_ceiling is None  # not cleared for confidential

    visible_to_high_ceiling = store.read(db, "project_memory", "proj-1", "sensitive-note", requester_ceiling="confidential")
    assert visible_to_high_ceiling is not None
    db.close()


def test_short_term_expires_via_ttl():
    db = SessionLocal()
    record, _ = store.write(db, "short_term", "task-1", "scratch", "temp value", actor="reasoning_engine")
    # Force it into the past rather than waiting 30 real minutes.
    record.ttl_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()

    assert store.read(db, "short_term", "task-1", "scratch") is None  # expire_stale runs inside read()
    expired_record = db.query(MemoryRecord).filter(MemoryRecord.id == record.id).first()
    assert expired_record.status == "expired"
    db.close()


def test_business_memory_write_requires_real_approval(security_layer_url):
    db = SessionLocal()
    record, outcome = store.write(
        db, "business_memory", "proj-1", "discount-rule", "orders over $10k get 5% off", actor="human_admin"
    )
    assert outcome["status"] == "pending_approval"
    assert outcome["approval_id"] is not None

    # not visible yet — it's pending, not active
    assert store.read(db, "business_memory", "proj-1", "discount-rule") is None

    import httpx
    httpx.post(f"{security_layer_url}/approval/{outcome['approval_id']}/decide", json={"decided_by": "human_admin", "approve": True})

    updated = store.reconcile_pending_approvals(db, "business_memory")
    assert len(updated) == 1
    assert updated[0].status == "active"

    now_visible = store.read(db, "business_memory", "proj-1", "discount-rule")
    assert now_visible is not None
    db.close()


def test_business_memory_rejected_stays_invisible(security_layer_url):
    db = SessionLocal()
    record, outcome = store.write(
        db, "business_memory", "proj-1", "bad-rule", "give everyone 100% off", actor="human_admin"
    )
    import httpx
    httpx.post(f"{security_layer_url}/approval/{outcome['approval_id']}/decide", json={"decided_by": "human_admin", "approve": False})

    store.reconcile_pending_approvals(db, "business_memory")
    assert store.read(db, "business_memory", "proj-1", "bad-rule") is None
    db.close()
