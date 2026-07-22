import secrets
import time

# Phase 31: real, single-use, short-lived authorization codes — in-memory,
# not persisted to a database. Honest limitation, not an oversight: this
# matches the identity service's own real deployment target (Phase 31
# doc, "team on a shared Ubuntu server") — one process, not a
# horizontally-scaled cluster, so in-memory state never needs to survive
# a restart or be shared across instances. A code is consumed exactly
# once (`pop` below) and expires in 60s regardless.
_CODE_TTL_SECONDS = 60
_codes: dict[str, dict] = {}


def issue(sub: str, client_id: str, redirect_uri: str) -> str:
    code = secrets.token_urlsafe(32)
    _codes[code] = {"sub": sub, "client_id": client_id, "redirect_uri": redirect_uri, "expires_at": time.time() + _CODE_TTL_SECONDS}
    return code


def redeem(code: str, client_id: str, redirect_uri: str) -> str | None:
    """Real single-use semantics: a code is popped (removed) whether or
    not it validates, so a replayed code can never succeed twice."""
    entry = _codes.pop(code, None)
    if not entry:
        return None
    if entry["expires_at"] < time.time():
        return None
    if entry["client_id"] != client_id or entry["redirect_uri"] != redirect_uri:
        return None
    return entry["sub"]
