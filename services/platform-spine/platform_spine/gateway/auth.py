from pathlib import Path
import yaml
from fastapi import Header, HTTPException

_TOKENS_FILE = Path(__file__).parent / "tokens.yaml"


def _load_tokens() -> dict:
    if _TOKENS_FILE.exists():
        return yaml.safe_load(_TOKENS_FILE.read_text()) or {}
    return {}


_tokens = _load_tokens()


def _resolve_token(token: str) -> str:
    actor = _tokens.get(token)
    if not actor:
        raise HTTPException(status_code=401, detail="invalid token")
    return actor


def resolve_actor(authorization: str = Header(default=None)) -> str:
    """
    STUB authentication. Maps a bearer token to an actor/role name via a
    local YAML file — a placeholder for real SSO/LDAP integration, which
    the Phase 2 design doc notes as a future extension point. Fine for
    local dev and testing; not real authentication.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing or malformed Authorization header")
    return _resolve_token(authorization[len("Bearer "):])


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
