import json

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

LOCAL_MODEL = "qwen3.5:4b"


def test_available_models_returns_real_ollama_tags(ollama_available):
    if not ollama_available:
        pytest.skip("Ollama not reachable at OLLAMA_URL")
    r = client.get("/reasoning/available_models")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["models"], list)
    assert len(body["models"]) > 0


def test_raw_generate_real_model_call_not_mocked(ollama_available):
    if not ollama_available:
        pytest.skip("Ollama not reachable at OLLAMA_URL")
    r = client.post(
        "/reasoning/raw_generate",
        json={"model": LOCAL_MODEL, "messages": [{"role": "user", "content": "Say the word banana and nothing else."}]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == LOCAL_MODEL
    assert "banana" in body["content"].lower()
    # Real usage counts from Ollama, not fabricated.
    assert body["prompt_eval_count"] > 0
    assert body["eval_count"] > 0


def test_raw_generate_unknown_model_fails_closed_not_silently(ollama_available):
    if not ollama_available:
        pytest.skip("Ollama not reachable at OLLAMA_URL")
    r = client.post(
        "/reasoning/raw_generate",
        json={"model": "definitely-not-a-real-model", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 404


def test_raw_generate_stream_yields_real_incremental_deltas(ollama_available):
    if not ollama_available:
        pytest.skip("Ollama not reachable at OLLAMA_URL")
    with client.stream(
        "POST", "/reasoning/raw_generate_stream",
        json={"model": LOCAL_MODEL, "messages": [{"role": "user", "content": "Count from 1 to 3."}]},
    ) as r:
        assert r.status_code == 200
        chunks = [json.loads(line[len("data: "):]) for line in r.iter_lines() if line.startswith("data: ")]

    assert len(chunks) > 1  # a real streamed response, not one shot pretending to stream
    assert chunks[-1]["done"] is True
    assert chunks[-1]["eval_count"] > 0
    # At least one non-final chunk carried real generated text.
    assert any(c["delta"] for c in chunks[:-1])
