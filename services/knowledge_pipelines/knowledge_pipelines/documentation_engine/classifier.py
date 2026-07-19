_VALID_TIERS = {"public", "internal", "confidential"}
_DEFAULT_TIER = "confidential"  # most restrictive — never leak content because classification metadata was missing


def assign_classification(explicit_classification: str = None) -> tuple[str, bool]:
    """
    Returns (classification, is_default). An explicit, valid classification
    from source metadata is honored as-is; anything missing or malformed
    defaults conservative — Documentation Engine is where un-vetted,
    human-authored content enters the system (Phase 9 doc), so ambiguity
    always resolves toward under-serving a query, never toward leaking.
    """
    if explicit_classification in _VALID_TIERS:
        return explicit_classification, False
    return _DEFAULT_TIER, True
