from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_verify_denies_unregistered_environment():
    r = client.post(
        "/security/verify_environment",
        json={"resolved_environment": "nonexistent_target", "capability": "testing_agent"},
    )
    assert r.status_code == 403


def test_verify_denies_production():
    r = client.post(
        "/security/verify_environment",
        json={"resolved_environment": "production_erp", "capability": "testing_agent"},
    )
    assert r.status_code == 403


def test_verify_allows_registered_sandbox():
    r = client.post(
        "/security/verify_environment",
        json={"resolved_environment": "test_sandbox_1", "capability": "testing_agent"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["is_sandbox"] is True
    assert body["verified"] == "allow"


def test_verify_logs_decision_to_audit_trail():
    client.post(
        "/security/verify_environment",
        json={"resolved_environment": "test_sandbox_1", "capability": "testing_agent"},
    )
    events = client.get("/audit/query?action=testing.verify_environment").json()
    assert len(events) >= 1
    assert events[-1]["resource"] == "test_sandbox_1"
    assert events[-1]["decision"] == "allow"


def test_verify_fails_closed_on_denied_target_too():
    client.post(
        "/security/verify_environment",
        json={"resolved_environment": "production_erp", "capability": "testing_agent"},
    )
    events = client.get("/audit/query?action=testing.verify_environment").json()
    denied = [e for e in events if e["resource"] == "production_erp"]
    assert len(denied) >= 1
    assert denied[-1]["decision"] == "deny"
