from pathlib import Path
import yaml
from fastapi import Header, HTTPException

_TOKENS_FILE = Path(__file__).parent / "tokens.yaml"


def _load_tokens() -> dict:
    if _TOKENS_FILE.exists():
        return yaml.safe_load(_TOKENS_FILE.read_text()) or {}
    return {}


_tokens = _load_tokens()


def resolve_actor(authorization: str = Header(default=None)) -> str:
    """
    STUB authentication — same convention as Gateway's own
    (platform_spine/gateway/auth.py), a local YAML token→actor map, not
    real SSO/LDAP (Phase 24 doc, Section 14 honesty note). The same
    token string the browser sends here is also sent verbatim to Gateway
    for task creation, and Gateway's own tokens.yaml maps it to the same
    actor name — two independent per-service token files, matching this
    project's established pattern (allowlists, PII registries) of
    per-service authorization data rather than one shared store.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing or malformed Authorization header")
    token = authorization[len("Bearer "):]
    actor = _tokens.get(token)
    if not actor:
        raise HTTPException(status_code=401, detail="invalid token")
    return actor


def resolve_bearer_token(authorization: str = Header(default=None)) -> str:
    """The raw token string, for forwarding to a peer service (platform-spine)
    that resolves its own actor identity from it independently."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing or malformed Authorization header")
    return authorization[len("Bearer "):]
