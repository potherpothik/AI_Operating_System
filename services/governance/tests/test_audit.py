from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_authorize_calls_are_logged():
    client.post(
        "/security/authorize",
        json={"actor": "odoo_agent", "action": "odoo.read_orm", "resource": "x"},
    )
    r = client.get("/audit/query")
    assert len(r.json()) >= 1


def test_hash_chain_is_valid():
    for i in range(5):
        client.post(
            "/security/authorize",
            json={"actor": "odoo_agent", "action": "odoo.read_orm", "resource": f"x{i}"},
        )
    r = client.get("/audit/verify")
    assert r.json()["valid"] is True
    assert r.json()["events_checked"] >= 5


def test_tampering_is_detected():
    """Simulates a compromised row and confirms verify_chain catches it."""
    client.post(
        "/security/authorize",
        json={"actor": "odoo_agent", "action": "odoo.read_orm", "resource": "y"},
    )
    from governance.db import SessionLocal
    from governance.models import AuditEvent

    db = SessionLocal()
    row = db.query(AuditEvent).first()
    row.action = "tampered.action"  # bypasses the API, edits the DB row directly
    db.commit()
    db.close()

    r = client.get("/audit/verify")
    assert r.json()["valid"] is False


def test_external_service_can_log_into_the_same_chain():
    r = client.post(
        "/audit/log",
        json={"actor_id": "context_builder", "actor_type": "service", "action": "context.build", "resource": "task-123"},
    )
    assert r.json()["logged"] is True

    events = client.get("/audit/query", params={"actor_id": "context_builder"}).json()
    assert len(events) == 1
    assert events[0]["action"] == "context.build"

    # it's part of the SAME hash chain, not a separate log
    assert client.get("/audit/verify").json()["valid"] is True


def test_query_filters_by_correlation_id():
    """Phase 18: the real gap-fill Security Agent's audit_query tool
    call needs — correlation_id is the standard way this system already
    threads a single task's related events together."""
    import uuid
    corr_id = str(uuid.uuid4())
    client.post(
        "/audit/log",
        json={"actor_id": "manufacturing_agent", "actor_type": "agent", "action": "manufacturing.propose_schedule_change", "resource": "task-corr-1", "correlation_id": corr_id},
    )
    client.post(
        "/audit/log",
        json={"actor_id": "manufacturing_agent", "actor_type": "agent", "action": "reasoning.allow", "resource": "task-corr-1", "correlation_id": corr_id},
    )
    # a real, different correlation_id that must NOT show up
    client.post(
        "/audit/log",
        json={"actor_id": "manufacturing_agent", "actor_type": "agent", "action": "reasoning.allow", "resource": "task-other", "correlation_id": str(uuid.uuid4())},
    )

    events = client.get("/audit/query", params={"correlation_id": corr_id}).json()
    assert len(events) == 2
    assert all(e["correlation_id"] == corr_id for e in events)


def test_stored_timestamp_survives_round_trip_as_the_same_utc_instant():
    """
    Regression test for a real bug: with a plain (non-timezone-aware)
    DateTime column, Postgres silently shifted a stored UTC instant by
    the session's timezone offset (confirmed directly against a live
    Postgres instance under a non-UTC session — a 12:00 UTC write came
    back as 08:00 with no tzinfo). DateTime(timezone=True) in models.py
    fixes this. This test would have caught the regression.
    """
    from datetime import datetime, timezone
    from governance.db import SessionLocal
    from governance.models import AuditEvent

    known = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)
    db = SessionLocal()
    row = AuditEvent(
        actor_id="probe", actor_type="agent", action="x", resource="y",
        decision="allow", this_hash="abc", ts=known, ts_iso=known.isoformat(),
    )
    db.add(row)
    db.commit()
    db.close()

    db = SessionLocal()
    fetched = db.query(AuditEvent).filter(AuditEvent.actor_id == "probe").first()
    db.close()

    # Normalize to UTC before stripping tzinfo — .replace(tzinfo=None) alone
    # would discard a non-UTC offset without converting first, which is a
    # real mistake this test itself made on the first pass (caught by
    # deliberately re-breaking the fix and confirming the test still
    # reported success when it shouldn't have).
    naive_known = known.astimezone(timezone.utc).replace(tzinfo=None)
    ts = fetched.ts if fetched.ts.tzinfo else fetched.ts.replace(tzinfo=timezone.utc)
    naive_fetched = ts.astimezone(timezone.utc).replace(tzinfo=None)
    assert naive_fetched == naive_known, (
        f"stored timestamp drifted from the original UTC instant: "
        f"expected {naive_known}, got {naive_fetched} — likely a non-timezone-aware column again"
    )
