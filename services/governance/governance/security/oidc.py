import os
import time

import httpx
import jwt
from jwt import algorithms

# Phase 31: real verification of a real OIDC identity token — signature,
# expiry, issuer all checked, not a stub. Governance is the one place
# every one of the 4 real consumers (Gateway, Control UI, MCP Surface,
# the OpenAI shim) already calls for authorize()/audit_log(); token
# verification lives here for the same reason, rather than each consumer
# fetching and caching its own JWKS copy independently.
IDENTITY_URL = os.environ.get("IDENTITY_URL", "http://localhost:8011")
_JWKS_CACHE_SECONDS = 300
_jwks_cache: dict = {"keys": None, "fetched_at": 0.0}


def _get_jwks() -> list[dict]:
    now = time.time()
    if _jwks_cache["keys"] is None or now - _jwks_cache["fetched_at"] > _JWKS_CACHE_SECONDS:
        resp = httpx.get(f"{IDENTITY_URL}/.well-known/jwks.json", timeout=5.0)
        resp.raise_for_status()
        _jwks_cache["keys"] = resp.json()["keys"]
        _jwks_cache["fetched_at"] = now
    return _jwks_cache["keys"]


def verify_token(token: str) -> dict | None:
    """Returns the real, verified claims on success, or None on any
    failure (unknown kid, bad signature, expired, wrong issuer) — a
    single fail-closed return path, same posture as every other
    governance check in this file's package."""
    try:
        header = jwt.get_unverified_header(token)
        jwks = _get_jwks()
        key_data = next((k for k in jwks if k["kid"] == header.get("kid")), None)
        if not key_data:
            return None
        public_key = algorithms.RSAAlgorithm.from_jwk(key_data)
        claims = jwt.decode(token, key=public_key, algorithms=["RS256"], issuer=IDENTITY_URL, options={"verify_aud": False})
        return claims
    except Exception:  # noqa: BLE001 — any verification failure is a real, uniform deny
        return None
