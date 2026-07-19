import os
from pathlib import Path
import yaml

REGISTRY_PATH = Path(os.environ.get("ENVIRONMENT_REGISTRY_PATH", Path(__file__).parent / "environment_registry.yaml"))


def _load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {}
    return yaml.safe_load(REGISTRY_PATH.read_text()) or {}


def verify(resolved_environment: str) -> dict:
    """
    Fail closed, same posture as secrets.resolve (Phase 7): an
    environment identifier not in the registry is NOT a sandbox, full
    stop — never "assume safe because we don't know better." This is the
    structural check the Phase 10 doc calls for: Testing Agent's
    execution target is verified here, not by policy convention or the
    agent's own claim about what it's about to run against.
    """
    registry = _load_registry()
    entry = registry.get(resolved_environment)
    if not entry:
        return {"is_sandbox": False, "reason": f"{resolved_environment!r} is not a registered environment"}
    is_sandbox = bool(entry.get("is_sandbox", False))
    return {"is_sandbox": is_sandbox, "reason": entry.get("description", "")}
