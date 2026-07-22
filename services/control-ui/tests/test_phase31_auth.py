import httpx
from fastapi.testclient import TestClient

from main import app
from control_ui import auth

client = TestClient(app)

_REDIRECT_URI = "http://localhost:8888/callback"
_CLIENT_ID = "aios-web"
_CLIENT_SECRET = "aios-web-dev-secret"


def _real_token(identity_url: str, username: str = "admin", password: str = "admin-dev-pw") -> str:
    login = httpx.post(
        f"{identity_url}/login",
        data={"username": username, "password": password, "client_id": _CLIENT_ID, "redirect_uri": _REDIRECT_URI},
        follow_redirects=False,
    )
    code = login.headers["location"].split("code=")[1].split("&")[0]
    token = httpx.post(
        f"{identity_url}/token",
        data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": _REDIRECT_URI,
            "client_id": _CLIENT_ID, "client_secret": _CLIENT_SECRET,
        },
    )
    return token.json()["access_token"]


def test_resolve_actor_stays_on_stub_path_by_default(monkeypatch):
    monkeypatch.setattr(auth, "AUTH_MODE", "stub")
    resp = client.get("/ui/bootstrap", headers={"Authorization": "Bearer dev-admin-token"})
    assert resp.status_code == 200


def test_decide_approval_end_to_end_under_oidc_records_the_real_per_user_identity(monkeypatch, full_stack, identity_url):
    """Real, full round trip: a real OIDC bearer token decides a real
    approval via Control UI, and governance's own record shows the real
    per-user sub as decided_by — not a shared "human_admin" stub name."""
    monkeypatch.setattr(auth, "AUTH_MODE", "oidc")
    monkeypatch.setattr(auth, "SECURITY_LAYER_URL", full_stack["governance"])
    from control_ui import clients as control_clients
    monkeypatch.setattr(control_clients, "SECURITY_LAYER_URL", full_stack["governance"])

    created = httpx.post(
        f"{full_stack['governance']}/approval/request",
        json={"action": "test.phase31_oidc_decide", "requested_by": "some_agent", "risk_tier": "medium"},
    ).json()

    token = _real_token(identity_url)
    r = client.post(f"/ui/approvals/{created['id']}/decide", json={"approve": True}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"

    fetched = httpx.get(f"{full_stack['governance']}/approval/{created['id']}").json()
    assert fetched["decided_by"] == "human-admin-001"
