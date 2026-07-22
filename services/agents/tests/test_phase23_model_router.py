import json
import uuid
import pytest

from agents.db import SessionLocal
from agents.reasoning_engine import loop, capability_registry, model_router
from agents.odoo_agent import register as odoo_agent_register

LOCAL_MODEL = "qwen3.5:4b"  # the one model genuinely pulled in this environment


def _ensure_ready(register_module, governance_url, assembly_url):
    import httpx
    db = SessionLocal()
    capability_registry.load_all(db)
    db.close()

    result = register_module.ensure_template_registered(created_by="test-suite")
    if result["registered"]:
        approval_id = result["result"]["approval_id"]
        httpx.post(f"{governance_url}/approval/{approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    httpx.post(f"{assembly_url}/prompt/templates/reconcile-approvals")


def _stub(action, **overrides):
    base = {
        "reasoning": "test reasoning", "answer_or_proposal": "test answer", "confidence": 0.9,
        "provenance": [], "risk_classification": "informational", "delegate_to": None, "action": action,
        "odoo_model": None, "odoo_domain_json": None, "odoo_fields_json": None,
    }
    base.update(overrides)
    return json.dumps(base)


@pytest.fixture(scope="session")
def ollama_available():
    return model_router.OllamaProvider().is_configured()


# ---------------------------------------------------------------------------
# OllamaProvider.has_model — real, against the real, live Ollama instance
# ---------------------------------------------------------------------------

def test_has_model_true_for_a_really_pulled_model(ollama_available):
    if not ollama_available:
        pytest.skip("Ollama not reachable")
    assert model_router.OllamaProvider().has_model(LOCAL_MODEL) is True


def test_has_model_false_for_a_model_that_genuinely_is_not_pulled(ollama_available):
    if not ollama_available:
        pytest.skip("Ollama not reachable")
    # The real, live gap this whole phase exists because of: confirmed
    # directly, this environment's Ollama instance has never had
    # "qwen-coder" pulled.
    assert model_router.OllamaProvider().has_model("qwen-coder") is False


# ---------------------------------------------------------------------------
# resolve_model — real fallback logic, live-verified against real Ollama
# ---------------------------------------------------------------------------

def test_resolve_model_falls_back_to_the_second_config_entry_when_first_is_unavailable(ollama_available):
    if not ollama_available:
        pytest.skip("Ollama not reachable")
    config = {"default_local_model": "qwen-coder", "fallback_local_model": LOCAL_MODEL}
    resolved = model_router.resolve_model(config)
    assert resolved == LOCAL_MODEL


def test_resolve_model_uses_the_first_entry_when_it_really_is_available(ollama_available):
    if not ollama_available:
        pytest.skip("Ollama not reachable")
    config = {"default_local_model": LOCAL_MODEL, "fallback_local_model": "deepseek-coder"}
    resolved = model_router.resolve_model(config)
    assert resolved == LOCAL_MODEL


def test_resolve_model_raises_when_nothing_configured_is_actually_available(ollama_available):
    if not ollama_available:
        pytest.skip("Ollama not reachable")
    config = {"default_local_model": "qwen-coder", "fallback_local_model": "deepseek-coder"}
    with pytest.raises(model_router.AllCandidatesExhausted):
        model_router.resolve_model(config)


def test_resolve_model_raises_with_no_config_at_all():
    with pytest.raises(model_router.AllCandidatesExhausted):
        model_router.resolve_model({})


# ---------------------------------------------------------------------------
# Cloud providers — real interface, genuinely never configured in this build
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("provider_cls,env_key", [
    (model_router.OpenAIProvider, "OPENAI_API_KEY"),
    (model_router.AnthropicProvider, "ANTHROPIC_API_KEY"),
    (model_router.GeminiProvider, "GOOGLE_API_KEY"),
])
def test_cloud_providers_are_honestly_not_configured(provider_cls, env_key, monkeypatch):
    monkeypatch.delenv(env_key, raising=False)
    provider = provider_cls()
    assert provider.is_configured() is False
    with pytest.raises(model_router.ProviderNotConfigured):
        provider.generate("some-model", "some prompt")


def test_cloud_provider_reports_configured_when_a_real_key_is_set(monkeypatch):
    # Confirms the check is real (reads the real env var), not hardcoded
    # to always return False — still never actually calls out anywhere.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    assert model_router.OpenAIProvider().is_configured() is True


# ---------------------------------------------------------------------------
# resolve_and_generate — the general-purpose dispatcher, real end to end
# ---------------------------------------------------------------------------

def test_resolve_and_generate_produces_a_real_completion(ollama_available):
    if not ollama_available:
        pytest.skip("Ollama not reachable")
    provider = model_router.OllamaProvider()
    text, provider_name, model_name = model_router.resolve_and_generate(
        "Reply with exactly one word: hello", candidates=[(provider, LOCAL_MODEL)],
    )
    assert provider_name == "ollama"
    assert model_name == LOCAL_MODEL
    assert isinstance(text, str) and len(text) > 0


def test_resolve_and_generate_skips_unavailable_candidates_before_a_real_one(ollama_available):
    if not ollama_available:
        pytest.skip("Ollama not reachable")
    provider = model_router.OllamaProvider()
    text, provider_name, model_name = model_router.resolve_and_generate(
        "Reply with exactly one word: hello",
        candidates=[(provider, "qwen-coder"), (provider, LOCAL_MODEL)],
    )
    assert model_name == LOCAL_MODEL


def test_resolve_and_generate_exhausts_and_raises_when_nothing_works(ollama_available):
    if not ollama_available:
        pytest.skip("Ollama not reachable")
    provider = model_router.OllamaProvider()
    with pytest.raises(model_router.AllCandidatesExhausted):
        model_router.resolve_and_generate(
            "unused", candidates=[(provider, "qwen-coder"), (provider, "deepseek-coder")],
        )


# ---------------------------------------------------------------------------
# Real, end-to-end integration: loop.execute() with target_model=None now
# genuinely resolves via the router, not a blind config trust — the exact
# gap this whole phase exists to close (Phase 23 doc, Section 0).
# ---------------------------------------------------------------------------

def test_execute_with_no_explicit_target_model_resolves_via_router_and_falls_back_for_real(
    full_stack, monkeypatch,
):
    _ensure_ready(odoo_agent_register, full_stack["governance"], full_stack["assembly"])

    def fake_config():
        # The real, live mismatch this environment actually has —
        # default_local_model isn't pulled, fallback_local_model is.
        return {"default_local_model": "qwen-coder", "fallback_local_model": LOCAL_MODEL, "external_model_allowed": False, "max_iterations": 8}

    from agents import clients
    monkeypatch.setattr(clients, "get_reasoning_engine_config", fake_config)

    def fake_generate(model, prompt):
        return _stub("odoo.read_orm", answer_or_proposal=f"answered using {model}")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id=f"model-router-test-{uuid.uuid4().hex[:8]}", task_description="Explain sale.order fields.",
        agent_capability="odoo_agent", namespace="default",
        # target_model deliberately omitted — the previously-dead
        # resolution path this phase makes real.
    )
    db.close()

    # The router really resolved to the fallback, not the unavailable default.
    assert execution.target_model == LOCAL_MODEL
    assert execution.status == "completed"
    assert LOCAL_MODEL in execution.result["answer_or_proposal"]
