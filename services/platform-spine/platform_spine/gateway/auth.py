import os
from pathlib import Path
import httpx
import yaml
from fastapi import Header, HTTPException

_TOKENS_FILE = Path(__file__).parent / "tokens.yaml"

# Phase 31: additive, not a breaking replacement — AUTH_MODE defaults to
# "stub" so the 30 prior phases of tests and dev workflows built against
# the fixed tokens.yaml→actor map keep working unchanged. AUTH_MODE=oidc
# is the new, real path: a bearer token is a real OIDC access token,
# verified against services/identity/ via governance's own
# /security/verify_token (Phase 31), and the resolved actor is the
# token's real per-user `sub`, not a shared stub name.
AUTH_MODE = os.environ.get("AUTH_MODE", "stub")
SECURITY_LAYER_URL = os.environ.get("SECURITY_LAYER_URL", "http://localhost:8000")


def _load_tokens() -> dict:
    if _TOKENS_FILE.exists():
        return yaml.safe_load(_TOKENS_FILE.read_text()) or {}
    return {}


_tokens = _load_tokens()


def _resolve_stub_token(token: str) -> str:
    actor = _tokens.get(token)
    if not actor:
        raise HTTPException(status_code=401, detail="invalid token")
    return actor


def _resolve_oidc_token(token: str) -> str:
    try:
        resp = httpx.post(f"{SECURITY_LAYER_URL}/security/verify_token", json={"token": token}, timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:  # noqa: BLE001 — fail closed, same posture as authorize()
        raise HTTPException(status_code=401, detail=f"identity verification unreachable: {e}")
    if not data.get("valid"):
        raise HTTPException(status_code=401, detail="invalid or expired token")
    return data["sub"]


def _resolve_token(token: str) -> str:
    if AUTH_MODE == "oidc":
        return _resolve_oidc_token(token)
    return _resolve_stub_token(token)


def resolve_actor(authorization: str = Header(default=None)) -> str:
    """
    AUTH_MODE=stub (default): maps a bearer token to an actor/role name
    via a local YAML file — a placeholder for real SSO/LDAP, unchanged
    since Phase 2. AUTH_MODE=oidc (Phase 31): real per-user identity, a
    real signed token verified against a real self-hosted OIDC provider.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing or malformed Authorization header")
    return _resolve_token(authorization[len("Bearer "):])


def resolve_raw_token_if_oidc(authorization: str = Header(default=None)) -> str | None:
    """
    Phase 31: the raw bearer token, only under AUTH_MODE=oidc — endpoints
    that call authorize() pass this through so governance can verify the
    token itself and authorize by its real role claim (see
    governance/security/api.py's own token-aware /authorize handling).
    Returns None under AUTH_MODE=stub, so every existing authorize()
    call site's behavior is completely unchanged by default.
    """
    if AUTH_MODE != "oidc" or not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization[len("Bearer "):]


def resolve_actor_for_stream(authorization: str = Header(default=None), token: str = None) -> str:
    """
    Phase 24 gap-fill: `EventSource` (the real browser SSE client Control
    UI uses) cannot set an `Authorization` header at all — a genuine
    browser API limitation, not something worth working around with a
    fake streaming layer. Scoped to this one query-param fallback, only
    for `GET /tasks/{id}/stream` — every other endpoint still requires
    the real header via `resolve_actor` above, unchanged.
    """
    if authorization and authorization.startswith("Bearer "):
        return _resolve_token(authorization[len("Bearer "):])
    if token:
        return _resolve_token(token)
    raise HTTPException(status_code=401, detail="missing bearer token (header or ?token=)")
