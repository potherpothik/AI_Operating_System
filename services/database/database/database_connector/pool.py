from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from database import clients

_ENGINES: dict[str, Engine] = {}


def get_engine(target_db: str, capability: str, correlation_id: str = "") -> Engine:
    """
    One pooled engine per target_db, created lazily on first use.
    Credentials are never held by this service directly — resolved via
    Security Layer on first connection and then reused for the pool's
    lifetime (Phase 7 doc: "credentials resolved via Security Layer.
    secrets.resolve, never stored directly"). A capability not permitted
    to resolve a given target's credentials fails closed here, before any
    connection is ever attempted.
    """
    if target_db in _ENGINES:
        return _ENGINES[target_db]

    connection_string = clients.resolve_secret(target_db, capability, correlation_id=correlation_id)
    engine = create_engine(connection_string, pool_size=5, max_overflow=2, pool_pre_ping=True)
    _ENGINES[target_db] = engine
    return engine


def reset():
    """Test-only: drop all cached engines so credential-resolution and
    pooling behavior can be exercised fresh per test."""
    for engine in _ENGINES.values():
        engine.dispose()
    _ENGINES.clear()
