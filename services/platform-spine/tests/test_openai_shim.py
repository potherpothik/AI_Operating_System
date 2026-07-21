from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

AUTH_IDE = {"Authorization": "Bearer dev-ide-client-token"}


def test_chat_completions_requires_auth():
    r = client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 401


def test_models_requires_auth():
    r = client.get("/v1/models")
    assert r.status_code == 401


def test_list_models_returns_real_ollama_tags(agents_url):
    r = client.get("/v1/models", headers=AUTH_IDE)
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "list"
    assert len(body["data"]) > 0
    assert all(m["object"] == "model" for m in body["data"])


def test_chat_completions_real_generation_not_mocked(agents_url):
    r = client.post(
        "/v1/chat/completions", headers=AUTH_IDE,
        json={"model": "qwen3.5:4b", "messages": [{"role": "user", "content": "Say the word banana and nothing else."}]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == "qwen3.5:4b"
    assert "banana" in body["choices"][0]["message"]["content"].lower()
    assert body["choices"][0]["finish_reason"] == "stop"
    # Real token counts from Ollama itself, not fabricated zeroes.
    assert body["usage"]["prompt_tokens"] > 0
    assert body["usage"]["completion_tokens"] > 0


def test_chat_completions_streams_real_sse_chunks(agents_url):
    with client.stream(
        "POST", "/v1/chat/completions", headers=AUTH_IDE,
        json={"model": "qwen3.5:4b", "messages": [{"role": "user", "content": "Count from 1 to 3."}], "stream": True},
    ) as r:
        assert r.status_code == 200
        lines = [line for line in r.iter_lines() if line.startswith("data: ")]

    assert lines[-1] == "data: [DONE]"
    assert any('"finish_reason": "stop"' in line for line in lines)
    # At least one real content delta arrived before the terminal chunks.
    assert any('"content"' in line for line in lines[:-2])


def test_chat_completions_structurally_bars_confidential_content_from_unrecognized_model(agents_url):
    """
    The one non-negotiable requirement this phase exists to enforce
    (forward-plan doc, Phase 27 scope): content classified above a
    candidate model's real ceiling never reaches the model at all.
    "gpt-4" is never a recognized local model, so assembly's real
    ceiling_for_model() returns "public" for it — any content that
    classifies above "public" (the classify default, "internal") must be
    refused before any real model call happens.
    """
    r = client.post(
        "/v1/chat/completions", headers=AUTH_IDE,
        json={"model": "gpt-4", "messages": [{"role": "user", "content": "Explain sale.order model internals."}]},
    )
    assert r.status_code == 403
    assert "ceiling" in r.json()["detail"]


def test_unknown_model_returns_a_clean_error_not_a_silent_fallback(agents_url):
    r = client.post(
        "/v1/chat/completions", headers=AUTH_IDE,
        json={"model": "definitely-not-a-real-model", "messages": [{"role": "user", "content": "hi"}]},
    )
    # Refused either for classification-ceiling reasons (public ceiling,
    # same as any other unrecognized name) or because the model plainly
    # isn't pulled — never a silent fallback to a different model.
    assert r.status_code in (403, 404)
