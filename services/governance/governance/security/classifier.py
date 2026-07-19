import re

_TIERS = ["public", "internal", "confidential"]

# Deliberately conservative, illustrative patterns — real deployments should
# extend this list. The point isn't exhaustive detection, it's that
# ambiguous or clearly-sensitive content never gets classified LESS
# restrictively than what's actually in it, matching Phase 1's
# default-conservative posture.
_CONFIDENTIAL_PATTERNS = [
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bpassword\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\b(api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"),  # credit-card-shaped number
]


def classify_content(content: str, declared_classification: str = "internal") -> dict:
    declared = declared_classification if declared_classification in _TIERS else "internal"
    floor = "public"

    for pattern in _CONFIDENTIAL_PATTERNS:
        if pattern.search(content or ""):
            floor = "confidential"
            break

    # Never return something less restrictive than either the declared
    # tier or the heuristic floor — take whichever is more restrictive.
    effective = declared if _TIERS.index(declared) >= _TIERS.index(floor) else floor
    return {
        "classification": effective,
        "declared_classification": declared,
        "heuristic_floor": floor,
    }
