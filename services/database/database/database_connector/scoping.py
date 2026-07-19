from pathlib import Path
import yaml

_TIERS = ["public", "internal", "confidential"]
CLASSIFICATION_DIR = Path(__file__).parent / "classification"


def _load(target_db: str) -> dict:
    path = CLASSIFICATION_DIR / f"{target_db}.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def tier_index(tier: str) -> int:
    # An unrecognized tier is treated as the MOST restrictive, never the
    # least — same fail-toward-restrictive posture as governance's own
    # classifier (Phase 1) and Context Builder's ceiling logic (Phase 4).
    return _TIERS.index(tier) if tier in _TIERS else _TIERS.index("confidential")


def column_classification(target_db: str, table: str, column: str) -> str:
    config = _load(target_db)
    table_config = config.get(table, {})
    return table_config.get(column, table_config.get("_default", "internal"))


def filter_columns(target_db: str, table: str, columns: list[str], requester_ceiling: str) -> tuple[list[str], list[str]]:
    """Returns (allowed, denied) column names for the given table, applied
    to actual result columns — not to the SQL text itself, since a bare
    string template can't be reliably parsed for exactly which columns a
    `SELECT *` will return (Phase 7 doc's `target_db`/scoping notes)."""
    ceiling_idx = tier_index(requester_ceiling)
    allowed, denied = [], []
    for col in columns:
        col_tier = column_classification(target_db, table, col)
        if tier_index(col_tier) <= ceiling_idx:
            allowed.append(col)
        else:
            denied.append(col)
    return allowed, denied
