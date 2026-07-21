import os
from enum import Enum

import httpx

from agents.reasoning_engine import ollama_adapter


class ModelType(str, Enum):
    """Naming matches elizaos-borrowed-ideas.md §5's own vocabulary
    (TEXT_LARGE, TEXT_EMBEDDING), not invented terms."""
    TEXT_LARGE = "text_large"
    CODE = "code"
    TEXT_EMBEDDING = "text_embedding"


class ProviderNotConfigured(Exception):
    pass


class AllCandidatesExhausted(Exception):
    pass


class ModelProvider:
    """Interface every provider implements. Real methods, no fabricated
    responses — an unconfigured provider is unreachable, never a fake
    success (Phase 23 doc, Section 2)."""

    name: str

    def is_configured(self) -> bool:
        raise NotImplementedError

    def has_model(self, model_name: str) -> bool:
        raise NotImplementedError

    def generate(self, model_name: str, prompt: str) -> str:
        raise NotImplementedError


class OllamaProvider(ModelProvider):
    """Real — wraps the same ollama_adapter every phase since 5 already
    used. The one genuinely new method is has_model(): a real GET
    /api/tags check that a candidate is actually pulled before trying to
    generate against it, the check that never existed before this phase
    (confirmed live: default_local_model='qwen-coder' isn't pulled in
    this environment, and nothing ever noticed until now)."""

    name = "ollama"

    def is_configured(self) -> bool:
        return ollama_adapter.is_reachable()

    def has_model(self, model_name: str) -> bool:
        try:
            resp = httpx.get(f"{ollama_adapter.OLLAMA_URL}/api/tags", timeout=5.0)
            resp.raise_for_status()
            names = {m["name"] for m in resp.json().get("models", [])}
            # Ollama tags include a ":latest" suffix some callers omit —
            # match both the exact name and its bare-tag form.
            return model_name in names or any(n.split(":")[0] == model_name for n in names)
        except Exception:  # noqa: BLE001
            return False

    def generate(self, model_name: str, prompt: str) -> str:
        return ollama_adapter.generate(model_name, prompt)

    def list_models(self) -> list[str]:
        """Phase 27: real, currently-pulled tags — used by /v1/models,
        not a hardcoded or config-derived list."""
        try:
            return ollama_adapter.list_models()
        except Exception:  # noqa: BLE001
            return []


class _EnvKeyCloudProvider(ModelProvider):
    """Real class, real interface — deliberately never reachable in this
    build. is_configured() checks for a real API key env var this
    offline-first system never sets (Phase 23 doc, Section 0's own
    alternatives-considered rejection of adding real external calls
    here). generate() on an unconfigured provider raises rather than
    returning anything — never a silent no-op success."""

    env_key: str

    def is_configured(self) -> bool:
        return bool(os.environ.get(self.env_key))

    def has_model(self, model_name: str) -> bool:
        return self.is_configured()

    def generate(self, model_name: str, prompt: str) -> str:
        if not self.is_configured():
            raise ProviderNotConfigured(f"{self.name}: {self.env_key} not set")
        raise NotImplementedError(f"{self.name}: real API call not implemented — interface only (Phase 23 doc, Section 0)")


class OpenAIProvider(_EnvKeyCloudProvider):
    name = "openai"
    env_key = "OPENAI_API_KEY"


class AnthropicProvider(_EnvKeyCloudProvider):
    name = "anthropic"
    env_key = "ANTHROPIC_API_KEY"


class GeminiProvider(_EnvKeyCloudProvider):
    name = "gemini"
    env_key = "GOOGLE_API_KEY"


def resolve_model(config: dict, ollama_provider: OllamaProvider = None) -> str:
    """
    The one function loop.py's execute() actually calls: turns
    default_local_model/fallback_local_model (real config keys since
    Phase 2, never actually checked against reality before this phase)
    into a model name genuinely confirmed available right now — never a
    blind trust of whichever value happens to be first in config.
    Deliberately does NOT call generate() itself — the existing
    generate(target_model, prompt) call site in loop.py stays completely
    unchanged, preserving the 46 existing tests across every phase since
    5 that monkeypatch loop.generate directly (Phase 23 doc, Section 3).
    """
    provider = ollama_provider or OllamaProvider()
    candidates = [m for m in (config.get("default_local_model"), config.get("fallback_local_model")) if m]
    reasons = []
    for model_name in candidates:
        if provider.has_model(model_name):
            return model_name
        reasons.append(f"{model_name!r} not available on {provider.name}")
    raise AllCandidatesExhausted(f"no configured local model is actually available: {'; '.join(reasons) or 'none configured'}")


def resolve_and_generate(prompt: str, candidates: list[tuple[ModelProvider, str]]) -> tuple[str, str, str]:
    """
    Tries each (provider, model_name) candidate in priority order —
    skips a candidate whose provider isn't configured or doesn't have
    that model, never silently skips a candidate that WOULD have worked.
    Returns (response_text, provider_name, model_name actually used).
    Raises AllCandidatesExhausted only once every candidate has been
    tried and failed, same fail-closed posture as OllamaUnavailable
    before this phase.
    """
    reasons = []
    for provider, model_name in candidates:
        if not provider.is_configured():
            reasons.append(f"{provider.name}: not configured")
            continue
        if not provider.has_model(model_name):
            reasons.append(f"{provider.name}: {model_name!r} not available")
            continue
        response = provider.generate(model_name, prompt)
        return response, provider.name, model_name
    raise AllCandidatesExhausted(f"no candidate produced a result: {'; '.join(reasons) or 'no candidates given'}")
