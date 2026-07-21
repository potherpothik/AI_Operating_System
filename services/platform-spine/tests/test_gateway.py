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


def test_get_task_events_reflects_real_transition_history(security_layer_url):
    # Phase 15: task_events() existed in task_manager/store.py since
    # Phase 2 but was never reachable over HTTP until this endpoint —
    # confirm it reports the real, ordered transition history, not just
    # the creation event.
    created = client.post("/api/v1/tasks", json={"title": "t"}, headers=AUTH_ODOO).json()
    task_id = created["id"]
    client.post(f"/api/v1/tasks/{task_id}/status", json={"status": "in_progress", "detail": "picked up"}, headers=AUTH_ODOO)

    r = client.get(f"/api/v1/tasks/{task_id}/events", headers=AUTH_ODOO)
    assert r.status_code == 200
    events = r.json()
    assert len(events) == 2
    assert events[0]["from_status"] is None and events[0]["to_status"] == "queued"
    assert events[1]["from_status"] == "queued" and events[1]["to_status"] == "in_progress"
    assert events[1]["detail"] == "picked up"


def test_get_events_for_unknown_task_returns_404(security_layer_url):
    r = client.get("/api/v1/tasks/nonexistent-id/events", headers=AUTH_ODOO)
    assert r.status_code == 404


def test_healthz():
    r = client.get("/healthz")
    assert r.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Phase 24 gap-fill: SSE stream accepts a ?token= fallback, since
# EventSource (the real browser client Control UI uses) cannot set an
# Authorization header at all. Unit-tested directly against the real
# resolver function rather than through a live streaming HTTP connection
# — TestClient's sync stream() never signals disconnect to the server's
# long-lived async generator, which then runs its full ~5-minute polling
# loop before the test process can proceed; this tests the exact same
# real code without that harness limitation.
# ---------------------------------------------------------------------------

def test_stream_auth_accepts_bearer_header():
    from platform_spine.gateway.auth import resolve_actor_for_stream
    assert resolve_actor_for_stream(authorization="Bearer dev-odoo-agent-token", token=None) == "odoo_agent"


def test_stream_auth_accepts_token_query_param_when_no_header():
    from platform_spine.gateway.auth import resolve_actor_for_stream
    assert resolve_actor_for_stream(authorization=None, token="dev-odoo-agent-token") == "odoo_agent"


def test_stream_auth_rejects_missing_auth_entirely():
    from fastapi import HTTPException
    from platform_spine.gateway.auth import resolve_actor_for_stream
    try:
        resolve_actor_for_stream(authorization=None, token=None)
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 401


def test_stream_auth_rejects_invalid_token_query_param():
    from fastapi import HTTPException
    from platform_spine.gateway.auth import resolve_actor_for_stream
    try:
        resolve_actor_for_stream(authorization=None, token="garbage")
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 401


# ---------------------------------------------------------------------------
# Phase 24 gap-fill: conversations + task.conversation_id
# ---------------------------------------------------------------------------

def test_create_and_list_conversations(security_layer_url):
    created = client.post("/api/v1/conversations", json={"title": "Sale order questions"}, headers=AUTH_ODOO).json()
    assert created["title"] == "Sale order questions"
    assert created["created_by"] == "odoo_agent"
    assert created["archived_at"] is None

    fetched = client.get(f"/api/v1/conversations/{created['id']}", headers=AUTH_ODOO).json()
    assert fetched["id"] == created["id"]

    listing = client.get("/api/v1/conversations", headers=AUTH_ODOO).json()
    assert any(c["id"] == created["id"] for c in listing)


def test_get_unknown_conversation_returns_404(security_layer_url):
    r = client.get("/api/v1/conversations/nonexistent-id", headers=AUTH_ODOO)
    assert r.status_code == 404


def test_task_threads_into_its_conversation(security_layer_url):
    conversation = client.post("/api/v1/conversations", json={"title": "Threading test"}, headers=AUTH_ODOO).json()
    task = client.post(
        "/api/v1/tasks",
        json={"title": "explain sale.order fields", "conversation_id": conversation["id"]},
        headers=AUTH_ODOO,
    ).json()
    assert task["conversation_id"] == conversation["id"]

    listed = client.get("/api/v1/tasks", params={"conversation_id": conversation["id"]}, headers=AUTH_ODOO).json()
    assert len(listed) == 1
    assert listed[0]["id"] == task["id"]

    # A task with no conversation_id at all still works — threading is optional.
    untethered = client.post("/api/v1/tasks", json={"title": "no thread"}, headers=AUTH_ODOO).json()
    assert untethered["conversation_id"] is None
