import httpx
from fastapi.testclient import TestClient

from main import app
from platform_spine.gateway import auth

client = TestClient(app)

_REDIRECT_URI = "http://localhost:8888/callback"
_CLIENT_ID = "aios-web"
_CLIENT_SECRET = "aios-web-dev-secret"


def _real_token(identity_url: str) -> str:
    login = httpx.post(
        f"{identity_url}/login",
        data={"username": "admin", "password": "admin-dev-pw", "client_id": _CLIENT_ID, "redirect_uri": _REDIRECT_URI},
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
    """AUTH_MODE unset/"stub" — Phase 2's original behavior, completely
    unchanged by Phase 31's addition."""
    monkeypatch.setattr(auth, "AUTH_MODE", "stub")
    assert auth._resolve_token("dev-odoo-agent-token") == "odoo_agent"


def test_resolve_actor_via_real_oidc_token(monkeypatch, security_layer_url, identity_url):
    """The real, live path: AUTH_MODE=oidc, a real signed token from the
    real identity service, verified through the real, live governance
    /security/verify_token — resolves to the token's real per-user sub,
    not a shared stub actor name."""
    monkeypatch.setattr(auth, "AUTH_MODE", "oidc")
    monkeypatch.setattr(auth, "SECURITY_LAYER_URL", security_layer_url)

    token = _real_token(identity_url)
    actor = auth._resolve_token(token)
    assert actor == "human-admin-001"


def test_resolve_actor_via_oidc_rejects_garbage_token(monkeypatch, security_layer_url, identity_url):
    from fastapi import HTTPException

    monkeypatch.setattr(auth, "AUTH_MODE", "oidc")
    monkeypatch.setattr(auth, "SECURITY_LAYER_URL", security_layer_url)

    try:
        auth._resolve_token("not-a-real-token")
        assert False, "expected HTTPException"
    except HTTPException as e:
        assert e.status_code == 401


def test_create_task_end_to_end_under_oidc_auth_mode(monkeypatch, security_layer_url, identity_url):
    """Real, full round trip: a real OIDC bearer token creates a real
    task via Gateway, and the created task's requested_by is the real
    per-user identity, not the fixed "human_admin"/"odoo_agent" stub
    names every other test in this file uses."""
    monkeypatch.setattr(auth, "AUTH_MODE", "oidc")
    monkeypatch.setattr(auth, "SECURITY_LAYER_URL", security_layer_url)

    token = _real_token(identity_url)
    r = client.post("/api/v1/tasks", json={"title": "phase31 oidc task"}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["requested_by"] == "human-admin-001"


def test_openai_shim_list_models_end_to_end_under_oidc(monkeypatch, security_layer_url, identity_url, agents_url):
    """The OpenAI-compatible endpoint (Phase 27) shares Gateway's own
    auth.py — confirming its authorize() calls also thread the real
    token through, not just Gateway's own task-creation path."""
    monkeypatch.setattr(auth, "AUTH_MODE", "oidc")
    monkeypatch.setattr(auth, "SECURITY_LAYER_URL", security_layer_url)

    token = _real_token(identity_url)
    r = client.get("/v1/models", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["object"] == "list"
