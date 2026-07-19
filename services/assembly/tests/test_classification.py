from fastapi.testclient import TestClient

from assembly.context_builder.classification import ceiling_for_model
from assembly.context_builder.api import model_ceiling
from main import app

client = TestClient(app)


def test_model_ceiling_endpoint_matches_the_underlying_function(platform_url):
    """
    Phase 11: Code Analysis Engine's raw_source_gate.py calls this over
    HTTP rather than duplicating classification.py's logic — this just
    confirms the endpoint is a genuine passthrough, not a second,
    divergent implementation.
    """
    assert model_ceiling("qwen-coder") == ceiling_for_model("qwen-coder")
    assert model_ceiling("gpt-4-some-external-api")["ceiling"] == "public"


def test_model_ceiling_reachable_over_real_http_routing(platform_url):
    """
    Regression test for a real bug: GET /context/model-ceiling was
    originally registered AFTER GET /context/{context_id} in the router,
    so FastAPI matched "model-ceiling" as a context_id and 404'd before
    ever reaching this handler — invisible to a direct function call
    (the test above), only caught by an actual HTTP request through the
    real route table.
    """
    resp = client.get("/context/model-ceiling", params={"target_model": "qwen-coder"})
    assert resp.status_code == 200
    assert resp.json()["ceiling"] == "confidential"


def test_local_model_gets_confidential_ceiling(platform_url):
    result = ceiling_for_model("qwen-coder")  # matches services/platform-spine's reasoning_engine.yaml default
    assert result["ceiling"] == "confidential"


def test_unrecognized_external_model_gets_public_ceiling(platform_url):
    result = ceiling_for_model("gpt-4-some-external-api")
    assert result["ceiling"] == "public"


def test_unreachable_config_fails_toward_most_restrictive(monkeypatch):
    import assembly.clients as clients

    monkeypatch.setattr(clients, "PLATFORM_URL", "http://localhost:1")  # nothing listens here
    result = ceiling_for_model("qwen-coder")
    assert result["ceiling"] == "public"  # fails closed, not "assume local and trusted"
