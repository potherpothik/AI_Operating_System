import json
import os
import time
import httpx

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
_MAX_RETRIES = 2
_BACKOFF_SECONDS = 1.0
_TIMEOUT_SECONDS = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "120"))


class OllamaUnavailable(Exception):
    pass


def generate(model: str, prompt: str) -> str:
    """
    Calls Ollama's /api/generate with retries and bounded backoff. Raises
    OllamaUnavailable after exhausting retries rather than hanging the
    reasoning loop indefinitely (Phase 5 doc, Reasoning Engine failure
    handling).

    think=False: confirmed via live testing that thinking-capable models
    (e.g. qwen3.5) otherwise spend their entire output token budget on
    internal chain-of-thought and hit done_reason="length" with an empty
    "response" field before ever writing the actual answer. Structured
    JSON output doesn't need visible reasoning exposed anyway — the
    "reasoning" field in the response schema already carries that.
    """
    last_error = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = httpx.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False, "think": False},
                timeout=_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            body = resp.json()
            return body.get("response", "")
        except Exception as e:  # noqa: BLE001 — any failure (connection, timeout, bad status) is retryable the same way
            last_error = e
            if attempt < _MAX_RETRIES:
                time.sleep(_BACKOFF_SECONDS * (attempt + 1))
    raise OllamaUnavailable(f"model call to {model!r} failed after {_MAX_RETRIES + 1} attempts: {last_error}")


def is_reachable() -> bool:
    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5.0)
        return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def list_models() -> list[str]:
    """Phase 27: the real, currently-pulled model tags — used by
    /v1/models and by model_router's default-resolution, not a
    hardcoded list."""
    resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5.0)
    resp.raise_for_status()
    return [m["name"] for m in resp.json().get("models", [])]


def chat(model: str, messages: list[dict]) -> dict:
    """
    Phase 27: Ollama's real /api/chat — messages-native, unlike
    generate()'s single prompt string, the shape an OpenAI-compatible
    /v1/chat/completions shim actually needs. Same think=False rationale
    as generate() (Phase 5/25's own found bug: a thinking-capable model
    otherwise burns its whole output budget on invisible chain-of-thought
    and returns empty content). Returns the raw parsed response dict —
    callers get real prompt_eval_count/eval_count token usage from
    Ollama itself, not fabricated zeroes.
    """
    resp = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={"model": model, "messages": messages, "stream": False, "think": False},
        timeout=_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()


def chat_stream(model: str, messages: list[dict]):
    """
    Phase 27: real token-by-token streaming from Ollama's /api/chat
    (stream=true) — genuine newline-delimited JSON chunks as the model
    actually generates them, not a complete response chunked
    artificially after the fact. Yields each parsed chunk dict; the
    final one has done=True.
    """
    with httpx.stream(
        "POST", f"{OLLAMA_URL}/api/chat",
        json={"model": model, "messages": messages, "stream": True, "think": False},
        timeout=_TIMEOUT_SECONDS,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            yield json.loads(line)
