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
    STUB authentication. Maps a bearer token to an actor/role name via a
    local YAML file — a placeholder for real SSO/LDAP integration, which
    the Phase 2 design doc notes as a future extension point. Fine for
    local dev and testing; not real authentication.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing or malformed Authorization header")
    token = authorization[len("Bearer "):]
    actor = _tokens.get(token)
    if not actor:
        raise HTTPException(status_code=401, detail="invalid token")
    return actor
