from assembly.context_builder.classification import ceiling_for_model


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
