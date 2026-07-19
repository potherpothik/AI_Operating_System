# The two-tier split IS this phase's security design (Phase 11 doc,
# Section 0). Structural content — signatures, docstrings, call graph —
# is internal by default: still not public, since a signature alone can
# leak proprietary algorithm shape or business logic, but freely
# retrievable via Vector Search like any other Phase 9 content. Raw
# function/class bodies are confidential by default, reachable only
# through the explicit, approval-gated raw_source_gate.py path, never
# auto-ingested anywhere.
STRUCTURAL_CLASSIFICATION = "internal"
RAW_SOURCE_CLASSIFICATION = "confidential"

_TIERS = ["public", "internal", "confidential"]


def tier_index(tier: str) -> int:
    """Same ordering assembly's classification.py uses — a model-ceiling
    response has to be compared against RAW_SOURCE_CLASSIFICATION by
    rank, not string equality, since "confidential" must mean "at least
    this restrictive," not "exactly this value.\""""
    return _TIERS.index(tier) if tier in _TIERS else 0
