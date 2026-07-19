from fastapi.testclient import TestClient
from main import app
from platform_spine.gateway import rate_limit

client = TestClient(app)

AUTH_ODOO = {"Authorization": "Bearer dev-odoo-agent-token"}
AUTH_ADMIN = {"Authorization": "Bearer dev-admin-token"}


def test_missing_auth_header_returns_401():
    r = client.post("/api/v1/tasks", json={"title": "x"})
    assert r.status_code == 401


def test_invalid_token_returns_401():
    r = client.post("/api/v1/tasks", json={"title": "x"}, headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


def test_rate_limit_kicks_in(security_layer_url):
    rate_limit.reset()
    for _ in range(60):
        client.post("/api/v1/tasks", json={"title": "x"}, headers=AUTH_ODOO)
    r = client.post("/api/v1/tasks", json={"title": "one too many"}, headers=AUTH_ODOO)
    assert r.status_code == 429


def test_create_task_calls_real_security_layer_and_succeeds(security_layer_url):
    r = client.post("/api/v1/tasks", json={"title": "explain sale.order fields"}, headers=AUTH_ODOO)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "queued"
    assert body["requested_by"] == "odoo_agent"
    assert "correlation_id" in body


def test_get_task_status(security_layer_url):
    created = client.post("/api/v1/tasks", json={"title": "t"}, headers=AUTH_ODOO).json()
    r = client.get(f"/api/v1/tasks/{created['id']}", headers=AUTH_ODOO)
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_get_unknown_task_returns_404(security_layer_url):
    r = client.get("/api/v1/tasks/nonexistent-id", headers=AUTH_ODOO)
    assert r.status_code == 404


def test_update_status_endpoint_enforces_state_machine(security_layer_url):
    created = client.post("/api/v1/tasks", json={"title": "t"}, headers=AUTH_ODOO).json()
    task_id = created["id"]

    ok = client.post(f"/api/v1/tasks/{task_id}/status", json={"status": "in_progress"}, headers=AUTH_ODOO)
    assert ok.status_code == 200
    assert ok.json()["status"] == "in_progress"

    bad = client.post(f"/api/v1/tasks/{task_id}/status", json={"status": "queued"}, headers=AUTH_ODOO)
    assert bad.status_code == 400


def test_healthz():
    r = client.get("/healthz")
    assert r.json()["status"] == "ok"
