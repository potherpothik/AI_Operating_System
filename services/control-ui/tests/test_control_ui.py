from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

AUTH_ADMIN = {"Authorization": "Bearer dev-admin-token"}


def test_healthz():
    assert client.get("/healthz").json()["status"] == "ok"


def test_ui_healthz():
    assert client.get("/ui/healthz").json()["status"] == "ok"


def test_bootstrap_requires_auth():
    r = client.get("/ui/bootstrap")
    assert r.status_code == 401


def test_bootstrap_reports_real_reachability(full_stack):
    r = client.get("/ui/bootstrap", headers=AUTH_ADMIN)
    assert r.status_code == 200
    body = r.json()
    assert body["actor"] == "human_admin"
    assert body["services"]["governance"] is True
    assert body["services"]["platform_spine"] is True
    # capability_views honestly empty — no view-manifest convention exists yet
    assert body["capability_views"] == []


def test_create_and_list_conversation_through_bff(full_stack):
    created = client.post("/ui/conversations", json={"title": "Test thread"}, headers=AUTH_ADMIN)
    assert created.status_code == 200
    conv = created.json()
    assert conv["title"] == "Test thread"

    fetched = client.get(f"/ui/conversations/{conv['id']}", headers=AUTH_ADMIN)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == conv["id"]

    listing = client.get("/ui/conversations", headers=AUTH_ADMIN)
    assert any(c["id"] == conv["id"] for c in listing.json())


def test_unknown_conversation_returns_404(full_stack):
    r = client.get("/ui/conversations/nonexistent-id", headers=AUTH_ADMIN)
    assert r.status_code == 404


def test_timeline_merges_real_tasks_and_events(full_stack):
    conv = client.post("/ui/conversations", json={"title": "Timeline test"}, headers=AUTH_ADMIN).json()

    # Create a real task threaded to this conversation directly against
    # platform-spine's own Gateway — the same path the browser will use.
    import httpx
    task = httpx.post(
        f"{full_stack['platform']}/api/v1/tasks",
        json={"title": "explain sale.order fields", "conversation_id": conv["id"]},
        headers=AUTH_ADMIN,
    ).json()

    r = client.get(f"/ui/conversations/{conv['id']}/timeline", headers=AUTH_ADMIN)
    assert r.status_code == 200
    body = r.json()
    assert body["partial"] is False
    assert len(body["turns"]) == 1
    assert body["turns"][0]["task"]["id"] == task["id"]
    assert body["turns"][0]["events"][0]["to_status"] == "queued"


def test_approvals_inbox_lists_real_pending_requests(full_stack):
    import httpx
    httpx.post(
        f"{full_stack['governance']}/approval/request",
        json={"action": "coding_gateway.propose_run", "requested_by": "coding_agent_gateway", "risk_tier": "high", "payload_ref": "test proposal"},
    )
    r = client.get("/ui/approvals/inbox", headers=AUTH_ADMIN)
    assert r.status_code == 200
    inbox = r.json()
    assert any(a["action"] == "coding_gateway.propose_run" for a in inbox)


def test_decide_approval_is_governed_and_forwards_for_real(full_stack):
    import httpx
    created = httpx.post(
        f"{full_stack['governance']}/approval/request",
        json={"action": "coding_gateway.propose_run", "requested_by": "coding_agent_gateway", "risk_tier": "high", "payload_ref": "test proposal 2"},
    ).json()

    r = client.post(f"/ui/approvals/{created['id']}/decide", json={"approve": True, "comment": "looks fine"}, headers=AUTH_ADMIN)
    assert r.status_code == 200
    assert r.json()["status"] == "approved"

    # Confirmed against governance directly, not just trusting the BFF's own response.
    fetched = httpx.get(f"{full_stack['governance']}/approval/{created['id']}").json()
    assert fetched["status"] == "approved"
    assert fetched["decided_by"] == "human_admin"


def test_views_catalog_is_honestly_empty():
    r = client.get("/ui/views")
    assert r.json() == {"views": []}
