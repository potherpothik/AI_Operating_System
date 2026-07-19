import fnmatch
import os
from pathlib import Path

CODEOWNERS_PATH = Path(os.environ.get("CODEOWNERS_PATH", Path(__file__).parent / "CODEOWNERS"))


def _load() -> list[tuple[str, str]]:
    entries = []
    if not CODEOWNERS_PATH.exists():
        return entries
    for line in CODEOWNERS_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        entries.append((parts[0], parts[1]))
    return entries


def owner_for(path: str) -> str | None:
    """CODEOWNERS convention: last matching pattern wins, so specific
    overrides come after general ones — this scans in file order and
    keeps the last match, not the first."""
    match = None
    for pattern, owner in _load():
        if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path, pattern.rstrip("/") + "/*"):
            match = owner
    return match


def owners_for_files(paths: list[str]) -> set[str]:
    owners = set()
    for path in paths:
        owner = owner_for(path)
        if owner:
            owners.add(owner)
    return owners
