import os
from pathlib import Path
import yaml

REGISTRY_PATH = Path(os.environ.get("SECRETS_REGISTRY_PATH", Path(__file__).parent / "secrets_registry.yaml"))


class SecretNotFound(Exception):
    pass


class SecretAccessDenied(Exception):
    pass


def _load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {}
    return yaml.safe_load(REGISTRY_PATH.read_text()) or {}


def resolve(target_db: str, capability: str) -> dict:
    """
    STUB indirection, same honesty posture as Phase 2's token->role file:
    the checked-in registry never holds a real credential, only which
    environment variable to read and which capabilities may read it — a
    real deployment would swap this for an actual vault (Vault, AWS
    Secrets Manager, etc.) lookup behind the same function signature.
    Fail closed: an unregistered target, a capability not on the allow
    list, or a missing env var all raise rather than falling back to
    anything.
    """
    registry = _load_registry()
    entry = registry.get(target_db)
    if not entry:
        raise SecretNotFound(f"no secret registered for target_db {target_db!r}")

    allowed = entry.get("allowed_capabilities", [])
    if capability not in allowed and "*" not in allowed:
        raise SecretAccessDenied(f"{capability!r} is not permitted to resolve credentials for {target_db!r}")

    env_var = entry["connection_string_env"]
    value = os.environ.get(env_var)
    if not value:
        raise SecretNotFound(f"{env_var!r} is not set in this environment — no credential material available")

    return {"target_db": target_db, "connection_string": value}
