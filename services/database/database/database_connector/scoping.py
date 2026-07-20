from pathlib import Path
import yaml

_TIERS = ["public", "internal", "confidential"]
CLASSIFICATION_DIR = Path(__file__).parent / "classification"
PII_REGISTRY_PATH = CLASSIFICATION_DIR / "pii_registry.yaml"


def _load(target_db: str) -> dict:
    path = CLASSIFICATION_DIR / f"{target_db}.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def _load_pii_registry() -> dict:
    if not PII_REGISTRY_PATH.exists():
        return {}
    return yaml.safe_load(PII_REGISTRY_PATH.read_text()) or {}


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
    `SELECT *` will return (Phase 7 doc's `target_db`/scoping notes).

    PII-tagged columns (Phase 15) are skipped here entirely — they're not
    a point on this scale at all, "a dimension separate from
    internal/confidential" (Phase 15 doc, Section 3), governed
    exclusively by filter_pii_columns below. Without this exclusion, a
    capability with a deliberately-kept-low ceiling (Sales Agent: internal,
    never confidential) could never see an explicitly-authorized,
    explicitly-requested PII field even though the whole point of the
    PII registry is to grant exactly that in a scoped way — the ceiling
    would silently veto the PII gate's own "yes" before it ever ran."""
    ceiling_idx = tier_index(requester_ceiling)
    pii_tagged = set(pii_columns(target_db, table))
    allowed, denied = [], []
    for col in columns:
        if col in pii_tagged:
            continue
        col_tier = column_classification(target_db, table, col)
        if tier_index(col_tier) <= ceiling_idx:
            allowed.append(col)
        else:
            denied.append(col)
    return allowed, denied


def pii_columns(target_db: str, table: str) -> list[str]:
    """Columns tagged as carrying identifiable personal data — a
    dimension separate from public/internal/confidential (Phase 15 doc,
    Section 3): a legal-category distinction, not a stricter point on the
    same classification scale."""
    registry = _load_pii_registry()
    return registry.get(target_db, {}).get("pii_columns", {}).get(table, [])


def capability_authorized_for_pii(target_db: str, capability: str) -> bool:
    """An unrecognized target or a capability absent from its
    authorized_capabilities list is never authorized — fail closed, same
    posture as tier_index's unrecognized-tier handling above."""
    registry = _load_pii_registry()
    return capability in registry.get(target_db, {}).get("authorized_capabilities", [])


def filter_pii_columns(target_db: str, table: str, columns: list[str], pii_fields_requested: list[str]) -> tuple[list[str], list[str]]:
    """The exclusive gate for PII-tagged columns among `columns` — a true
    second dimension, not a restriction layered on top of filter_columns:
    non-PII columns are entirely outside this function's concern (they
    never appear in its output at all; filter_columns handles those), and
    a PII-tagged column's fate here has nothing to do with its
    classification tier or the requester's ceiling. A PII column is
    allowed only if it was explicitly named in this specific request's
    pii_fields_requested. Callers must authorize the capability for PII
    access (see capability_authorized_for_pii) BEFORE calling this — an
    unauthorized request for a PII field is a 403 at the API layer, not a
    silent exclusion here. This function only enforces "minimum
    necessary, named per task": a PII column absent from
    pii_fields_requested (e.g. pulled in incidentally by SELECT *) is
    excluded the same as any other denied column."""
    tagged = set(pii_columns(target_db, table))
    allowed, denied = [], []
    for col in columns:
        if col not in tagged:
            continue
        if col in pii_fields_requested:
            allowed.append(col)
        else:
            denied.append(col)
    return allowed, denied
