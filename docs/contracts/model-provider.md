# `ModelProvider` contract — v1

Formalizes `services/agents/agents/reasoning_engine/model_router.py`
(Phase 23), unchanged by this document — this is a description of real,
already-implemented code, not a new interface being introduced.

## Interface

```python
class ModelProvider:
    name: str

    def is_configured(self) -> bool:
        """Real check — a real API key env var set, or a real reachable
        local endpoint. Never returns True for something that would
        fail on the next call."""

    def has_model(self, model_name: str) -> bool:
        """Real check that this SPECIFIC model is available on this
        provider right now — not just that the provider is configured."""

    def generate(self, model_name: str, prompt: str) -> str:
        """Real model call. Raises rather than returning a fabricated
        response on any failure (ProviderNotConfigured, or the
        provider's own transport error) — an unconfigured provider is
        unreachable, never a fake success."""
```

## Real implementations (v1)

| Provider | `is_configured()` | Status |
|---|---|---|
| `OllamaProvider` | real `GET /api/tags` reachability check | **Live** — every agent's actual model calls since Phase 5 |
| `OpenAIProvider` | `OPENAI_API_KEY` env var set | Real interface, honestly `not_configured` — never set in this offline-first build |
| `AnthropicProvider` | `ANTHROPIC_API_KEY` env var set | Real interface, honestly `not_configured` |
| `GeminiProvider` | `GOOGLE_API_KEY` env var set | Real interface, honestly `not_configured` |

## Selection

`resolve_model(config, provider)` — real candidate resolution:
`default_local_model` then `fallback_local_model` from
`services/platform-spine/platform_spine/config_manager/files/reasoning_engine.yaml`,
in order, returning the first one `has_model()` confirms is actually
available. Raises `AllCandidatesExhausted` rather than guessing if none
are. `resolve_and_generate(prompt, candidates)` extends this to
multi-provider candidate lists (provider, model_name) pairs, trying each
in order — the shape a future real cloud-provider activation would use
without changing this contract.

## Consumers (v1)

- `services/agents/agents/reasoning_engine/loop.py` — the full agentic
  pipeline (`execute()`'s `target_model=None` path).
- `services/agents/agents/reasoning_engine/api.py`'s
  `/reasoning/raw_generate`/`raw_generate_stream` (Phase 27) — raw,
  non-agentic chat completions behind the OpenAI-compatible shim.

## A real bug this contract's own enforcement surfaced (Phase 27)

`ceiling_for_model()` (`services/assembly/`, Phase 4/11 — a consumer of
this SAME config, not of this Python interface directly) read
`default_local_model`/`fallback_local_model` to decide which models
count as "local" for classification-ceiling purposes, independently of
`resolve_model()`'s own live-availability check. When the config value
was stale (never actually pulled), `resolve_model()` correctly routed
around it, but `ceiling_for_model()` silently mis-classified the real
local model as external. Fixed at the config source in Phase 27, not by
adding a second workaround — see
`docs/aios-architecture-and-phases.md#phase-27-openai-compatible-endpoint`
Section 3.

## Versioning

v1 = the interface as it exists after Phase 27. A breaking change (new
required method, changed return shape) increments to v2 and this file is
copied to `model-provider-v1.md`, matching how `services/assembly/`
already versions prompt templates (Phase 4) rather than silently
rewriting history in place.
