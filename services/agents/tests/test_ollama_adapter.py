import httpx
import pytest

from agents.reasoning_engine import ollama_adapter


class _FakeResponse:
    def __init__(self, status_code=200, json_body=None):
        self.status_code = status_code
        self._json = json_body or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json


def test_generate_returns_response_text(monkeypatch):
    def fake_post(url, json, timeout):
        return _FakeResponse(200, {"response": "hello from the model"})

    monkeypatch.setattr(httpx, "post", fake_post)
    result = ollama_adapter.generate("qwen3.5:4b", "say hi")
    assert result == "hello from the model"


def test_generate_retries_then_raises_after_exhausting_attempts(monkeypatch):
    calls = {"count": 0}

    def fake_post(url, json, timeout):
        calls["count"] += 1
        raise httpx.ConnectError("connection refused", request=None)

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(ollama_adapter.time, "sleep", lambda s: None)  # don't actually wait in tests

    with pytest.raises(ollama_adapter.OllamaUnavailable):
        ollama_adapter.generate("qwen3.5:4b", "say hi")
    assert calls["count"] == ollama_adapter._MAX_RETRIES + 1


def test_generate_succeeds_after_transient_failure(monkeypatch):
    calls = {"count": 0}

    def fake_post(url, json, timeout):
        calls["count"] += 1
        if calls["count"] < 2:
            raise httpx.ConnectError("connection refused", request=None)
        return _FakeResponse(200, {"response": "recovered"})

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(ollama_adapter.time, "sleep", lambda s: None)

    result = ollama_adapter.generate("qwen3.5:4b", "say hi")
    assert result == "recovered"
    assert calls["count"] == 2


def test_live_ollama_generate(ollama_available):
    if not ollama_available:
        pytest.skip("Ollama not reachable at OLLAMA_URL")
    result = ollama_adapter.generate("qwen3.5:4b", "Reply with exactly the word: OK")
    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_requests_thinking_disabled(monkeypatch):
    """
    Regression test: confirmed via live testing against qwen3.5 (a
    thinking-capable model) that without think=False, the model spends its
    entire output budget on internal chain-of-thought and returns
    response="" with done_reason="length" — never actually answering.
    Caught by reading the raw API response, not by the JSON-validity check
    alone (empty string parses as invalid JSON either way, so this could
    have looked like "the model just produced bad output" without digging
    into *why*).
    """
    captured = {}

    def fake_post(url, json, timeout):
        captured.update(json)
        return _FakeResponse(200, {"response": "{}"})

    monkeypatch.setattr(httpx, "post", fake_post)
    ollama_adapter.generate("qwen3.5:4b", "prompt")
    assert captured["think"] is False


def test_live_generate_actually_produces_response_not_empty_string(ollama_available):
    """
    The specific failure mode this was chasing: response="" with
    done_reason="length" from a thinking model that never got to its
    answer. A live call against the real thinking-capable model, not a
    mock, since the mock can't reproduce the model's own token-budget
    behavior.
    """
    if not ollama_available:
        pytest.skip("Ollama not reachable at OLLAMA_URL")
    result = ollama_adapter.generate(
        "qwen3.5:4b",
        'Respond ONLY with this exact JSON object: {"answer": "ok"}',
    )
    assert result.strip() != ""
