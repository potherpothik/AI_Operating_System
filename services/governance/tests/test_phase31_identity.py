import httpx
from fastapi.testclient import TestClient

from main import app
from governance.approval import api as approval_api

client = TestClient(app)

_REDIRECT_URI = "http://localhost:8888/callback"
_CLIENT_ID = "aios-web"
_CLIENT_SECRET = "aios-web-dev-secret"


def _real_token(identity_url: str, username: str = "admin", password: str = "admin-dev-pw") -> str:
    """A real, full Authorization Code round trip against the real,
    live identity service — no mocking of the HTTP calls or the crypto."""
    login_resp = httpx.post(
        f"{identity_url}/login",
        data={"username": username, "password": password, "client_id": _CLIENT_ID, "redirect_uri": _REDIRECT_URI},
        follow_redirects=False,
    )
    assert login_resp.status_code == 302, login_resp.text
    code = login_resp.headers["location"].split("code=")[1].split("&")[0]

    token_resp = httpx.post(
        f"{identity_url}/token",
        data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": _REDIRECT_URI,
            "client_id": _CLIENT_ID, "client_secret": _CLIENT_SECRET,
        },
    )
    assert token_resp.status_code == 200, token_resp.text
    return token_resp.json()["access_token"]


def test_login_with_wrong_password_is_rejected(identity_url):
    resp = httpx.post(
        f"{identity_url}/login",
        data={"username": "admin", "password": "definitely-wrong", "client_id": _CLIENT_ID, "redirect_uri": _REDIRECT_URI},
    )
    assert resp.status_code == 401


def test_authorization_code_is_single_use(identity_url):
    login_resp = httpx.post(
        f"{identity_url}/login",
        data={"username": "admin", "password": "admin-dev-pw", "client_id": _CLIENT_ID, "redirect_uri": _REDIRECT_URI},
        follow_redirects=False,
    )
    code = login_resp.headers["location"].split("code=")[1].split("&")[0]
    body = {
        "grant_type": "authorization_code", "code": code, "redirect_uri": _REDIRECT_URI,
        "client_id": _CLIENT_ID, "client_secret": _CLIENT_SECRET,
    }
    first = httpx.post(f"{identity_url}/token", data=body)
    assert first.status_code == 200
    second = httpx.post(f"{identity_url}/token", data=body)
    assert second.status_code == 400, "a redeemed authorization code must never be usable twice"


def test_jwks_and_discovery_are_real_and_consistent(identity_url):
    discovery = httpx.get(f"{identity_url}/.well-known/openid-configuration").json()
    jwks = httpx.get(f"{identity_url}/.well-known/jwks.json").json()
    assert discovery["jwks_uri"] == f"{identity_url}/.well-known/jwks.json"
    assert len(jwks["keys"]) == 1
    assert jwks["keys"][0]["kty"] == "RSA"


def test_governance_verify_token_accepts_a_real_identity_token(identity_url):
    token = _real_token(identity_url)
    resp = client.post("/security/verify_token", json={"token": token})
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["sub"] == "human-admin-001"
    assert body["email"] == "admin@aios.local"
    assert body["role"] == "human_admin"


def test_governance_verify_token_rejects_garbage():
    resp = client.post("/security/verify_token", json={"token": "not.a.real.jwt"})
    assert resp.status_code == 200
    assert resp.json() == {"valid": False}


def test_approver_not_requester_enforcement_when_enabled(monkeypatch):
    """
    Phase 31: with ENFORCE_APPROVER_NOT_REQUESTER on, deciding your own
    request must be refused — the exact scenario that's meaningless
    under shared stub auth (every request AND decision is "human_admin")
    but becomes real once distinct per-user identities exist.
    """
    monkeypatch.setattr(approval_api, "ENFORCE_APPROVER_NOT_REQUESTER", True)

    created = client.post("/approval/request", json={"action": "test.self_approve", "requested_by": "user-a", "risk_tier": "medium"})
    request_id = created.json()["id"]

    self_decision = client.post(f"/approval/{request_id}/decide", json={"decided_by": "user-a", "approve": True})
    assert self_decision.json() == {"error": "approver must not be the same identity as the requester"}

    other_decision = client.post(f"/approval/{request_id}/decide", json={"decided_by": "user-b", "approve": True})
    assert other_decision.json()["status"] == "approved"


def test_approver_not_requester_not_enforced_by_default():
    """The default (ENFORCE_APPROVER_NOT_REQUESTER unset/false) must keep
    every prior phase's stub-auth workflow — self-decision by the shared
    "human_admin" actor — working exactly as it always has."""
    created = client.post("/approval/request", json={"action": "test.self_approve_default", "requested_by": "human_admin", "risk_tier": "medium"})
    request_id = created.json()["id"]
    decision = client.post(f"/approval/{request_id}/decide", json={"decided_by": "human_admin", "approve": True})
    assert decision.json()["status"] == "approved"
