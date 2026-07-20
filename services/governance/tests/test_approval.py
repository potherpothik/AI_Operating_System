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


def test_list_all_includes_both_pending_and_decided():
    """Phase 13: GET /approval (bare) is the general listing /pending
    never was — Metrics Dashboard needs decided requests too, to compute
    time-to-decision, not just the still-open queue."""
    pending_r = client.post("/approval/request", json={"action": "odoo.propose_change", "requested_by": "odoo_agent"})
    pending_id = pending_r.json()["id"]

    decided_r = client.post("/approval/request", json={"action": "odoo.propose_change", "requested_by": "odoo_agent"})
    decided_id = decided_r.json()["id"]
    client.post(f"/approval/{decided_id}/decide", json={"decided_by": "human_admin", "approve": True})

    all_requests = client.get("/approval").json()
    ids = {r["id"] for r in all_requests}
    assert pending_id in ids
    assert decided_id in ids

    decided_entry = next(r for r in all_requests if r["id"] == decided_id)
    assert decided_entry["status"] == "approved"
    assert decided_entry["decided_at"] is not None
    assert decided_entry["created_at"] is not None


def test_list_all_filters_by_status():
    r = client.post("/approval/request", json={"action": "odoo.propose_change", "requested_by": "odoo_agent"})
    req_id = r.json()["id"]
    client.post(f"/approval/{req_id}/decide", json={"decided_by": "human_admin", "approve": False})

    rejected_only = client.get("/approval?status=rejected").json()
    assert any(r["id"] == req_id for r in rejected_only)
    assert all(r["status"] == "rejected" for r in rejected_only)


# ---------------------------------------------------------------------------
# Phase 16 — approval-review attachment: a second agent's advisory input,
# additional context for the human approver, never a decision itself.
# ---------------------------------------------------------------------------

def test_attach_review_shows_up_on_get_request():
    r = client.post("/approval/request", json={"action": "manufacturing.propose_schedule_change", "requested_by": "manufacturing_agent"})
    req_id = r.json()["id"]

    attach = client.post(
        f"/approval/{req_id}/attach_review",
        json={"reviewer_capability": "code_review_agent", "verdict": "recommend_approve", "reasoning": "No callers of the changed function found elsewhere."},
    )
    assert attach.json()["approval_id"] == req_id
    assert attach.json()["verdict"] == "recommend_approve"

    fetched = client.get(f"/approval/{req_id}")
    reviews = fetched.json()["reviews"]
    assert len(reviews) == 1
    assert reviews[0]["reviewer_capability"] == "code_review_agent"
    assert reviews[0]["reasoning"] == "No callers of the changed function found elsewhere."


def test_attach_review_to_unknown_approval_returns_error():
    r = client.post(
        "/approval/nonexistent-id/attach_review",
        json={"reviewer_capability": "code_review_agent", "verdict": "concern", "reasoning": "x"},
    )
    assert "error" in r.json()


def test_attach_review_never_changes_the_approval_decision_itself():
    """A review is additional context, never a vote — confirmed live:
    attaching a 'concern' review does not move status off pending, and
    a human's own decide() call afterward is completely unaffected by
    what was attached."""
    r = client.post("/approval/request", json={"action": "sales.propose_quote", "requested_by": "sales_agent"})
    req_id = r.json()["id"]

    client.post(f"/approval/{req_id}/attach_review", json={"reviewer_capability": "code_review_agent", "verdict": "concern", "reasoning": "risky"})
    still_pending = client.get(f"/approval/{req_id}").json()
    assert still_pending["status"] == "pending"
    assert still_pending["decided_by"] is None

    decide = client.post(f"/approval/{req_id}/decide", json={"decided_by": "human_admin", "approve": True})
    assert decide.json()["status"] == "approved"

    final = client.get(f"/approval/{req_id}").json()
    assert final["status"] == "approved"
    assert len(final["reviews"]) == 1  # the review survives the decision, unaltered


def test_multiple_reviews_accumulate_oldest_first():
    r = client.post("/approval/request", json={"action": "architecture.propose_decision", "requested_by": "architecture_agent"})
    req_id = r.json()["id"]

    client.post(f"/approval/{req_id}/attach_review", json={"reviewer_capability": "code_review_agent", "verdict": "concern", "reasoning": "first"})
    client.post(f"/approval/{req_id}/attach_review", json={"reviewer_capability": "code_review_agent", "verdict": "recommend_approve", "reasoning": "second"})

    reviews = client.get(f"/approval/{req_id}").json()["reviews"]
    assert [r["reasoning"] for r in reviews] == ["first", "second"]


def test_get_request_with_no_reviews_returns_empty_list_not_missing_key():
    r = client.post("/approval/request", json={"action": "odoo.propose_change", "requested_by": "odoo_agent"})
    req_id = r.json()["id"]
    fetched = client.get(f"/approval/{req_id}").json()
    assert fetched["reviews"] == []
