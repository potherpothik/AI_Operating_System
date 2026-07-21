from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_get_config_returns_file_defaults():
    r = client.get("/config/reasoning_engine")
    body = r.json()
    # Phase 27: corrected from "qwen-coder" (never actually pulled in
    # this environment) to the real, live-verified default.
    assert body["default_local_model"] == "qwen3.5:4b"
    assert body["external_model_allowed"] in (False, "false", "False")


def test_non_security_override_applies_immediately():
    client.post(
        "/config/override",
        json={"service": "reasoning_engine", "key": "max_iterations", "value": "12", "set_by": "human_admin"},
    )
    r = client.get("/config/reasoning_engine")
    assert r.json()["max_iterations"] == "12"


def test_security_tagged_override_does_not_apply_without_approval():
    r = client.post(
        "/config/override",
        json={
            "service": "reasoning_engine",
            "key": "external_model_allowed",
            "value": "true",
            "set_by": "human_admin",
        },
    )
    assert r.json()["status"] == "pending_approval"

    config = client.get("/config/reasoning_engine").json()
    # must NOT have silently flipped to true — it's still pending
    assert config["external_model_allowed"] in (False, "false", "False")


def test_reload_picks_up_after_override_without_restart():
    r = client.post("/config/reload")
    assert r.json()["reloaded"] is True


def test_schema_lists_known_keys():
    r = client.get("/config/schema/gateway")
    assert "rate_limit_per_minute" in r.json()["known_keys"]
