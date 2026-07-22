import os
from pathlib import Path
import httpx
import yaml
from fastapi import Header, HTTPException

_TOKENS_FILE = Path(__file__).parent / "tokens.yaml"

# Phase 31: same additive AUTH_MODE convention as Gateway's own
# (platform_spine/gateway/auth.py) — "stub" (default) keeps the existing
# local token→actor map; "oidc" verifies a real bearer token against a
# real self-hosted identity provider via governance's own
# /security/verify_token, and resolves the real per-user `sub`.
AUTH_MODE = os.environ.get("AUTH_MODE", "stub")
SECURITY_LAYER_URL = os.environ.get("SECURITY_LAYER_URL", "http://localhost:8000")


def _load_tokens() -> dict:
    if _TOKENS_FILE.exists():
        return yaml.safe_load(_TOKENS_FILE.read_text()) or {}
    return {}


_tokens = _load_tokens()


def _resolve_oidc_token(token: str) -> str:
    try:
        resp = httpx.post(f"{SECURITY_LAYER_URL}/security/verify_token", json={"token": token}, timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:  # noqa: BLE001 — fail closed
        raise HTTPException(status_code=401, detail=f"identity verification unreachable: {e}")
    if not data.get("valid"):
        raise HTTPException(status_code=401, detail="invalid or expired token")
    return data["sub"]


def resolve_actor(authorization: str = Header(default=None)) -> str:
    """
    AUTH_MODE=stub (default): local YAML token→actor map, not real
    SSO/LDAP (Phase 24 doc, Section 14 honesty note) — the same token
    string the browser sends here is also sent verbatim to Gateway for
    task creation, and Gateway's own tokens.yaml maps it to the same
    actor name, two independent per-service token files. AUTH_MODE=oidc
    (Phase 31): real per-user identity from a real signed token.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing or malformed Authorization header")
    token = authorization[len("Bearer "):]
    if AUTH_MODE == "oidc":
        return _resolve_oidc_token(token)
    actor = _tokens.get(token)
    if not actor:
        raise HTTPException(status_code=401, detail="invalid token")
    return actor


def resolve_raw_token_if_oidc(authorization: str = Header(default=None)) -> str | None:
    """Phase 31: same convention as Gateway's own — the raw bearer token,
    only under AUTH_MODE=oidc, so authorize() call sites can let
    governance verify it and authorize by its real role claim."""
    if AUTH_MODE != "oidc" or not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization[len("Bearer "):]


def resolve_bearer_token(authorization: str = Header(default=None)) -> str:
    """The raw token string, for forwarding to a peer service (platform-spine)
    that resolves its own actor identity from it independently."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing or malformed Authorization header")
    return authorization[len("Bearer "):]
