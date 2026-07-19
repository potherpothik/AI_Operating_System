import json
from assembly.prompt_builder.schema_validate import validate_response, CANONICAL_SCHEMA


def _valid_response(**overrides):
    base = {
        "reasoning": "because the field tracks lifecycle state",
        "answer_or_proposal": "it tracks quotation through invoice",
        "confidence": 0.9,
        "provenance": ["item-1"],
        "risk_classification": "informational",
        "delegate_to": None,
    }
    base.update(overrides)
    return json.dumps(base)


def test_valid_response_passes():
    result = validate_response(_valid_response(), CANONICAL_SCHEMA)
    assert result["valid"] is True
    assert result["errors"] == []


def test_missing_field_fails():
    body = json.loads(_valid_response())
    del body["confidence"]
    result = validate_response(json.dumps(body), CANONICAL_SCHEMA)
    assert result["valid"] is False
    assert any("confidence" in e for e in result["errors"])


def test_confidence_out_of_range_fails():
    result = validate_response(_valid_response(confidence=1.5), CANONICAL_SCHEMA)
    assert result["valid"] is False
    assert any("out of range" in e for e in result["errors"])


def test_invalid_risk_classification_fails():
    result = validate_response(_valid_response(risk_classification="catastrophic"), CANONICAL_SCHEMA)
    assert result["valid"] is False


def test_not_json_fails_cleanly():
    result = validate_response("this is not json at all {{{", CANONICAL_SCHEMA)
    assert result["valid"] is False
    assert "not valid JSON" in result["errors"][0]


def test_wrong_type_fails():
    result = validate_response(_valid_response(provenance="not-a-list"), CANONICAL_SCHEMA)
    assert result["valid"] is False


def test_delegate_to_can_be_null_or_string():
    assert validate_response(_valid_response(delegate_to=None), CANONICAL_SCHEMA)["valid"] is True
    assert validate_response(_valid_response(delegate_to="database_agent"), CANONICAL_SCHEMA)["valid"] is True
