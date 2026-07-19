from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_approval_lifecycle_approve():
    r = client.post(
        "/approval/request",
        json={"action": "odoo.propose_change", "requested_by": "odoo_agent", "risk_tier": "medium"},
    )
    req_id = r.json()["id"]
    assert r.json()["status"] == "pending"

    pending = client.get("/approval/pending").json()
    assert any(p["id"] == req_id for p in pending)

    decide = client.post(
        f"/approval/{req_id}/decide",
        json={"decided_by": "human_admin", "approve": True},
    )
    assert decide.json()["status"] == "approved"

    # decided requests drop off the pending list
    pending_after = client.get("/approval/pending").json()
    assert not any(p["id"] == req_id for p in pending_after)


def test_approval_rejected():
    r = client.post(
        "/approval/request",
        json={"action": "risky.thing", "requested_by": "odoo_agent"},
    )
    req_id = r.json()["id"]
    decide = client.post(
        f"/approval/{req_id}/decide",
        json={"decided_by": "human_admin", "approve": False},
    )
    assert decide.json()["status"] == "rejected"


def test_decision_on_unknown_request_returns_error():
    r = client.post(
        "/approval/nonexistent-id/decide",
        json={"decided_by": "human_admin", "approve": True},
    )
    assert "error" in r.json()


def test_get_specific_request_by_id():
    r = client.post(
        "/approval/request",
        json={"action": "odoo.propose_change", "requested_by": "odoo_agent"},
    )
    req_id = r.json()["id"]

    fetched = client.get(f"/approval/{req_id}")
    assert fetched.json()["status"] == "pending"

    client.post(f"/approval/{req_id}/decide", json={"decided_by": "human_admin", "approve": True})
    fetched_after = client.get(f"/approval/{req_id}")
    assert fetched_after.json()["status"] == "approved"


def test_pending_route_not_shadowed_by_id_wildcard():
    """/pending is a literal path registered before /{request_id} — confirms it still resolves correctly."""
    r = client.get("/approval/pending")
    assert isinstance(r.json(), list)
