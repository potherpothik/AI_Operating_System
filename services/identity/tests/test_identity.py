import jwt as pyjwt

from tests.conftest import client

_REDIRECT_URI = "http://localhost:8888/callback"
_CLIENT_ID = "aios-web"
_CLIENT_SECRET = "aios-web-dev-secret"


def _get_code(username="admin", password="admin-dev-pw"):
    resp = client.post(
        "/login",
        data={"username": username, "password": password, "client_id": _CLIENT_ID, "redirect_uri": _REDIRECT_URI},
        follow_redirects=False,
    )
    assert resp.status_code == 302, resp.text
    return resp.headers["location"].split("code=")[1].split("&")[0]


def test_discovery_document_is_real_and_self_consistent():
    body = client.get("/.well-known/openid-configuration").json()
    assert body["authorization_endpoint"].endswith("/authorize")
    assert body["token_endpoint"].endswith("/token")
    assert "RS256" in body["id_token_signing_alg_values_supported"]


def test_jwks_exposes_the_real_public_key():
    body = client.get("/.well-known/jwks.json").json()
    assert len(body["keys"]) == 1
    key = body["keys"][0]
    assert key["kty"] == "RSA"
    assert key["alg"] == "RS256"
    assert "n" in key and "e" in key


def test_authorize_rejects_unknown_client():
    resp = client.get("/authorize", params={"response_type": "code", "client_id": "not-a-real-client", "redirect_uri": _REDIRECT_URI})
    assert resp.status_code == 400


def test_authorize_rejects_unregistered_redirect_uri():
    resp = client.get("/authorize", params={"response_type": "code", "client_id": _CLIENT_ID, "redirect_uri": "http://evil.example/cb"})
    assert resp.status_code == 400


def test_authorize_renders_a_real_login_form():
    resp = client.get("/authorize", params={"response_type": "code", "client_id": _CLIENT_ID, "redirect_uri": _REDIRECT_URI})
    assert resp.status_code == 200
    assert "<form" in resp.text
    assert 'name="username"' in resp.text


def test_login_wrong_password_rejected():
    resp = client.post("/login", data={"username": "admin", "password": "wrong", "client_id": _CLIENT_ID, "redirect_uri": _REDIRECT_URI})
    assert resp.status_code == 401


def test_full_authorization_code_flow_issues_a_real_verifiable_jwt():
    code = _get_code()
    token_resp = client.post(
        "/token",
        data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": _REDIRECT_URI,
            "client_id": _CLIENT_ID, "client_secret": _CLIENT_SECRET,
        },
    )
    assert token_resp.status_code == 200
    body = token_resp.json()
    assert body["token_type"] == "Bearer"

    jwks = client.get("/.well-known/jwks.json").json()["keys"][0]
    from jwt.algorithms import RSAAlgorithm
    public_key = RSAAlgorithm.from_jwk(jwks)
    claims = pyjwt.decode(body["access_token"], key=public_key, algorithms=["RS256"], options={"verify_aud": False})
    assert claims["sub"] == "human-admin-001"
    assert claims["email"] == "admin@aios.local"
    assert claims["role"] == "human_admin"


def test_token_exchange_rejects_wrong_client_secret():
    code = _get_code()
    resp = client.post(
        "/token",
        data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": _REDIRECT_URI,
            "client_id": _CLIENT_ID, "client_secret": "wrong-secret",
        },
    )
    assert resp.status_code == 401


def test_authorization_code_cannot_be_replayed():
    code = _get_code()
    body = {
        "grant_type": "authorization_code", "code": code, "redirect_uri": _REDIRECT_URI,
        "client_id": _CLIENT_ID, "client_secret": _CLIENT_SECRET,
    }
    first = client.post("/token", data=body)
    assert first.status_code == 200
    second = client.post("/token", data=body)
    assert second.status_code == 400


def test_userinfo_requires_a_real_bearer_token():
    resp = client.get("/userinfo")
    assert resp.status_code == 401


def test_userinfo_returns_real_claims_for_a_valid_token():
    code = _get_code()
    token = client.post(
        "/token",
        data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": _REDIRECT_URI,
            "client_id": _CLIENT_ID, "client_secret": _CLIENT_SECRET,
        },
    ).json()["access_token"]
    resp = client.get("/userinfo", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["sub"] == "human-admin-001"


def test_second_registered_user_gets_a_distinct_identity():
    code = _get_code(username="operator", password="operator-dev-pw")
    token = client.post(
        "/token",
        data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": _REDIRECT_URI,
            "client_id": _CLIENT_ID, "client_secret": _CLIENT_SECRET,
        },
    ).json()["access_token"]
    resp = client.get("/userinfo", headers={"Authorization": f"Bearer {token}"})
    assert resp.json()["sub"] == "operator-002"
