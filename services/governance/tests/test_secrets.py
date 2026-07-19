import os
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_resolve_unregistered_target_returns_404():
    r = client.post("/security/secrets/resolve", json={"target_db": "nonexistent_target", "capability": "database_agent"})
    assert r.status_code == 404


def test_resolve_denies_capability_not_on_allow_list():
    r = client.post("/security/secrets/resolve", json={"target_db": "demo_erp", "capability": "odoo_agent"})
    assert r.status_code == 403


def test_resolve_fails_closed_when_env_var_not_set(monkeypatch):
    monkeypatch.delenv("DEMO_ERP_DATABASE_URL", raising=False)
    r = client.post("/security/secrets/resolve", json={"target_db": "demo_erp", "capability": "database_agent"})
    assert r.status_code == 404


def test_resolve_returns_real_connection_string_when_configured(monkeypatch):
    monkeypatch.setenv("DEMO_ERP_DATABASE_URL", "postgresql://test:test@localhost/demo_erp")
    r = client.post("/security/secrets/resolve", json={"target_db": "demo_erp", "capability": "database_agent"})
    assert r.status_code == 200
    assert r.json()["connection_string"] == "postgresql://test:test@localhost/demo_erp"


def test_resolve_never_logs_the_actual_credential_value(monkeypatch):
    """The audit trail records that a resolution happened, and for which
    target/capability — never the resolved secret material itself."""
    monkeypatch.setenv("DEMO_ERP_DATABASE_URL", "postgresql://sensitive_user:sensitive_pw@localhost/demo_erp")
    client.post("/security/secrets/resolve", json={"target_db": "demo_erp", "capability": "database_agent"})

    events = client.get("/audit/query?action=secrets.resolve").json()
    assert len(events) >= 1
    for event in events:
        assert "sensitive_pw" not in str(event)
        assert "sensitive_user" not in str(event)
