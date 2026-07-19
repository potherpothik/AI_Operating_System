import json

_VALID_RISK_TIERS = {"informational", "low", "medium", "high"}

_TYPE_CHECKS = {
    "str": lambda v: isinstance(v, str),
    "float": lambda v: isinstance(v, (int, float)),
    "list": lambda v: isinstance(v, list),
    "optional_str": lambda v: v is None or isinstance(v, str),
}


def validate_response(raw_response: str, expected_schema: dict) -> dict:
    try:
        parsed = json.loads(raw_response)
    except (json.JSONDecodeError, TypeError) as e:
        return {"valid": False, "errors": [f"not valid JSON: {e}"]}

    if not isinstance(parsed, dict):
        return {"valid": False, "errors": ["response is not a JSON object"]}

    errors = []
    for field, type_name in expected_schema.items():
        if field not in parsed:
            errors.append(f"missing required field: {field}")
            continue
        check = _TYPE_CHECKS.get(type_name)
        if check and not check(parsed[field]):
            errors.append(f"field {field!r} expected type {type_name}, got {type(parsed[field]).__name__}")

    if "confidence" in parsed and isinstance(parsed["confidence"], (int, float)):
        if not (0.0 <= parsed["confidence"] <= 1.0):
            errors.append(f"confidence {parsed['confidence']} out of range [0.0, 1.0]")

    if "risk_classification" in parsed and parsed["risk_classification"] not in _VALID_RISK_TIERS:
        errors.append(f"risk_classification {parsed['risk_classification']!r} not one of {_VALID_RISK_TIERS}")

    return {"valid": len(errors) == 0, "errors": errors, "parsed": parsed if not errors else None}


CANONICAL_SCHEMA = {
    "reasoning": "str",
    "answer_or_proposal": "str",
    "confidence": "float",
    "provenance": "list",
    "risk_classification": "str",
    "delegate_to": "optional_str",
}
