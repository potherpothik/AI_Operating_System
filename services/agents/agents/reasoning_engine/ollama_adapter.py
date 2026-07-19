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
