import fnmatch
from pathlib import Path
import yaml

ALLOWLIST_DIR = Path(__file__).parent / "allowlists"


def _load() -> dict:
    """
    One YAML file per agent_capability — new agents get shell access by
    adding a file here, not by editing this module (same discovery
    pattern as Phase 5's capability_registry).
    """
    result = {}
    for path in sorted(ALLOWLIST_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        result[data["agent_capability"]] = data.get("commands", [])
    return result


class NotAllowed(Exception):
    pass


def check(agent_capability: str, command: str, args: list[str], mode: str) -> tuple[bool, str]:
    """
    Default-deny: an agent_capability with no allowlist file, or a
    command/args combination matching no pattern, is rejected. Returns
    (allowed, reason).
    """
    allowlist = _load()
    entries = allowlist.get(agent_capability)
    if entries is None:
        return False, f"no command allowlist registered for {agent_capability!r}"

    full_command = " ".join([command] + list(args))
    for entry in entries:
        if fnmatch.fnmatch(full_command, entry["pattern"]):
            if entry["mode"] != mode:
                # Same command text can be declared read_only OR mutating never both —
                # a mismatch here means the caller mis-declared its own intent.
                continue
            return True, f"matched pattern {entry['pattern']!r}"

    return False, f"{full_command!r} (mode={mode}) matches no allowed pattern for {agent_capability!r}"
