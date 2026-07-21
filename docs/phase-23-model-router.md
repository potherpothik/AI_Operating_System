# Phase 23 — Model Router

---

## Prerequisites (read before implementation)

| Doc | Why |
|---|---|
| [`docs/README.md`](README.md) | Doc index and before-you-code checklist |
| [`phase-5-odoo-agent-reasoning-engine.md`](phase-5-odoo-agent-reasoning-engine.md) | Reasoning Engine's own `execute()` loop — the one call site this phase changes |
| [`elizaos-borrowed-ideas.md`](elizaos-borrowed-ideas.md) §5 | `useModel(ModelType, params)` — the pattern this phase borrows, not the runtime |
| [`architecture-vision.md`](architecture-vision.md) §3 | Model strategy seed this phase turns into a real phase doc |

---

## 0. Priority Decision: Why a Router Now, and What It Actually Fixes

**Why it exists here:** every phase through 22 called `ollama_adapter.generate(target_model, prompt)` directly — `target_model` a bare string, `default_local_model`/`fallback_local_model` two config keys that have existed since Phase 2 but were **never actually used** for fallback. Confirmed live in this exact environment: `reasoning_engine.yaml`'s `default_local_model: qwen-coder` names a model that **isn't pulled** in this Ollama instance (`GET /api/tags` returns only `qwen3.5:4b`) — every live-model test this whole session actually worked only because each test explicitly overrode `target_model` to `qwen3.5:4b`, silently routing around the dead default. A real router closes exactly this gap: resolve a model name for real, at call time, against what's actually available — not trust a config value that could be stale.

**Alternatives considered**
- *Leave `target_model` as a bare string forever, just fix the config typo* — rejected. Fixes today's specific mismatch but not the underlying problem: nothing has ever checked whether a configured model is actually pulled before using it, and nothing has ever used `fallback_local_model` for anything. The next stale config value reproduces the exact same silent failure.
- *Build real cloud provider integrations (OpenAI/Anthropic/Gemini) this phase* — rejected. This system is offline-first by explicit design (`architecture-vision.md` §0, `docs-and-honesty.mdc`); adding real external API calls means real credentials, real cost, real data egress of prompts (which may contain retrieved ERP/source content) — a security-relevant decision that needs its own explicit sign-off, not something to bundle into a router refactor. Interface only, honestly `not_configured` — same posture as Phase 22's OpenCode/Claude Code adapters before a Docker-isolated backend exists.
- *A shared cross-service `model_router` package* — rejected. This project has never shared code via a common package between services (every service is independently deployable; Phase 6/10's duplicated `_SAFE_ENV_KEYS`-style precedent already established this). The router lives in `services/agents/agents/reasoning_engine/` since that's the one real call site; `services/knowledge/`'s embedding model swap (`get_default_embedding_model()`, Phase 3) stays as its own, already-adequate mechanism — not force-merged into this router just for naming symmetry.
- *Rewrite `assembly/context_builder/classification.py`'s `ceiling_for_model()` to call into the router* — rejected. That function's contract (`target_model in {default_local_model, fallback_local_model}` → `confidential`, else `public`/`internal`) is real, tested, security-relevant code (Phase 4). The router is designed to preserve it exactly: whichever model name the router ultimately resolves to is still one of those two config values by construction — `resolve_model()` only ever returns `config.get("default_local_model")` or `config.get("fallback_local_model")`, never a third value — so classification's existing, already-passing test suite (`services/assembly/tests/test_classification.py`) needed zero changes (Section 6 below).

**Trade-offs:** the router only ever tries local Ollama models in practice this phase, since no cloud provider is really configured — from the outside, "smarter fallback between two local models" is the only observable behavior change. That's intentional: the typed registry and provider interface are the real, durable piece; a second real provider slots in later without touching `loop.py` again.

**Security implications:** no new external network path — `OllamaProvider` calls the same `OLLAMA_URL` every phase since 5 already called. Cloud provider classes exist as code but their `is_configured()` always returns `False` without a real API key env var, which this build never sets — they cannot be reached by any code path today.

**Performance implications:** one extra `GET /api/tags` call per resolution to confirm the candidate model is actually pulled — real, cheap (millisecond-scale, confirmed live), not worth caching away for this phase's scope.

**Future scalability:** a real second provider (say, a genuinely configured OpenAI key) becomes a second candidate in the same priority list, gated by Security Layer's `external_model_allowed` + classification ceiling exactly as `classification.py` already enforces — no new governance mechanism needed.

**Estimated complexity:** Low–Medium. One new module, one changed call site, zero new services, zero new config keys — `default_local_model`/`fallback_local_model` already existed.

---

## 1. Real, Typed Model Registry

Naming matches `elizaos-borrowed-ideas.md` §5's own vocabulary (`TEXT_LARGE`, `TEXT_EMBEDDING`) rather than inventing new terms:

```python
class ModelType(str, Enum):
    TEXT_LARGE = "text_large"        # general reasoning — every agent's generate() call today
    CODE = "code"                     # code-specialized — same provider pool as TEXT_LARGE for now, a distinct type for a future code-tuned model to register against
    TEXT_EMBEDDING = "text_embedding" # named for completeness — NOT rewired into services/knowledge/ this phase (Section 6)
```

## 2. Provider Interface (real, minimal)

```python
class ModelProvider:
    name: str
    def is_configured(self) -> bool: ...
    def has_model(self, model_name: str) -> bool: ...
    def generate(self, model_name: str, prompt: str) -> str: ...
```

**`OllamaProvider`** — real, wraps the exact same `ollama_adapter.generate()`/`is_reachable()` every phase since 5 already used, plus one genuinely new method: `has_model(name)`, a real `GET /api/tags` check confirming a candidate model is actually pulled before trying to generate against it — the check that was missing entirely before this phase.

**`OpenAIProvider` / `AnthropicProvider` / `GeminiProvider`** — real classes, real interface, `is_configured()` checks for a real env var (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`) that this build never sets. `generate()` on an unconfigured provider raises `ProviderNotConfigured` rather than being reachable at all — never a fabricated response, never a silent no-op success.

## 3. Router Dispatch (real fallback, live-verified)

Two real, separately-usable functions — deliberately not one, per the wiring
decision below:

```python
def resolve_model(config: dict, ollama_provider: OllamaProvider = None) -> str:
    """The one function loop.py actually calls: turns default_local_model/
    fallback_local_model into a model name genuinely confirmed available
    right now (a real GET /api/tags check), trying each in priority
    order. Raises AllCandidatesExhausted if neither is actually pulled."""

def resolve_and_generate(prompt: str, candidates: list[tuple[ModelProvider, str]]) -> tuple[str, str, str]:
    """The general-purpose version: tries each (provider, model_name)
    candidate in priority order across ANY provider (not just Ollama —
    this is where a real second provider would plug in), and actually
    calls generate() on the first one that's configured and available.
    Returns (response_text, provider_name, model_name actually used)."""
```

**A deliberate wiring decision, not the originally-sketched one:** `loop.py`'s
`execute()` calls `resolve_model()` only, to pick which model name to use —
it does **not** replace the existing `generate(target_model, prompt)` call
site with `resolve_and_generate()`. Real reason: 46 existing tests across
every phase since 5 monkeypatch `loop.generate` directly
(`monkeypatch.setattr(loop, "generate", fake_generate)`); replacing that
call site would mean touching every one of those tests for a router whose
only observable behavior change, in this environment, is picking between
two local Ollama models. `resolve_and_generate()` is real, tested, and
ready for a future call site (or a future second provider) without that
blast radius today.

**When a caller passes an explicit `target_model`** (every existing test
in this repo does, via `LOCAL_MODEL`), `resolve_model()` is never even
called — unchanged behavior, zero risk to the 20+ phases of tests already
passing against explicit overrides. The new resolution logic only
activates on the previously-dead, previously-untested `target_model=None`
path.

The model name `resolve_model()` returns is passed to
`build_context`/`render_prompt` exactly as `target_model` always was —
`classification.py`'s existing `ceiling_for_model()` check (Section 0)
needs zero changes, since the resolved name is still one of the two
configured local-model strings it already recognizes.

## 4. Failure Handling

Fails closed, same posture as every other phase: if neither configured
local model is actually available, `resolve_model()` raises
`AllCandidatesExhausted` — `loop.py` catches it and falls through to the
exact same value this code always defaulted to
(`config.get("default_local_model") or "qwen-coder"`), letting the
existing `OllamaUnavailable` handling a few lines later report the real
failure once `generate()` actually tries and fails — never inventing a
model name of its own, never silently retrying forever.

## 5. Explicitly Out of Scope

- Real cloud provider credentials/calls (Section 0) — interface only.
- Rewiring `services/knowledge/knowledge/vector_search/embedding.py`'s `TEXT_EMBEDDING` path through this router — Phase 3's own `get_default_embedding_model()` swap mechanism stays as-is; a future session can register it as a second `ModelType.TEXT_EMBEDDING` provider pool without touching Reasoning Engine.
- Per-agent model-type preference (e.g. `python_agent` preferring `ModelType.CODE` over `TEXT_LARGE`) — every agent still resolves the same `TEXT_LARGE` candidate list today; a real `CODE`-preferring agent is a config/capability.yaml change for a later session, not a router-architecture change.
- A settings UI for model routing — Control UI's own §5.6 (Settings) already named this as future scope.

---

## 6. Built (real code, live-verified — see `services/agents/README.md`)

Real module (`services/agents/agents/reasoning_engine/model_router.py`):
`ModelType`, `ModelProvider` interface, real `OllamaProvider` (wraps the
existing `ollama_adapter` plus a genuinely new `has_model()` check),
interface-only `OpenAIProvider`/`AnthropicProvider`/`GeminiProvider`, and
two dispatch functions — `resolve_model()` (what `loop.py` actually calls)
and `resolve_and_generate()` (the general-purpose version, real and
tested, not yet wired into a call site — Section 3's own wiring-decision
explains why).

`loop.py`'s `execute()` calls `resolve_model()` in place of the old blind
`config.get("default_local_model") or "qwen-coder"` line — the
`generate(target_model, prompt)` call site itself is unchanged, preserving
all 46 existing tests that monkeypatch `loop.generate` directly.

**Live-verified, not simulated:** `OllamaProvider().has_model("qwen-coder")`
returns `False` in this real environment — confirmed directly, this
Ollama instance has never had it pulled. A full `loop.execute()` run with
`target_model=None` and a config naming `qwen-coder` as
`default_local_model` and the real, actually-pulled `qwen3.5:4b` as
`fallback_local_model` genuinely resolved to `qwen3.5:4b` — checked on the
persisted `ReasoningExecution.target_model` field, not just the router's
own return value. `resolve_and_generate()` produced a real Ollama
completion end to end. `services/assembly/tests/test_classification.py`
needed zero changes and still passes, confirming Section 0's "resolves to
one of the two config values by construction" claim held in practice, not
just in the argument.

Full result in `services/agents/README.md`'s own Phase 23 section.

---

## Next

Nothing currently blocks Phase 23 from being the last item in the original
24-phase mandate. Real cloud provider support (a second, genuinely
configured `ModelProvider`) is the natural next increment when/if this
system's offline-first posture is deliberately relaxed for a specific,
approved use case — a product decision, not an engineering one.
