# GPU-Day Playbook

Real, rehearsed steps for the day this system moves from "current
hardware, local 4B-class model" to "a real GPU server available." Not
speculative — every config key and endpoint named below is real and
already live in this codebase (Phases 23/25/27); this playbook is a
checklist, not new code, per the forward plan's own framing of Phase 31.

## Preconditions

- A reachable Ollama instance on the GPU host (or any OpenAI-compatible
  server `ollama_adapter.py`/`model_router.py` can already reach —
  confirm via `curl $OLLAMA_URL/api/tags`).
- The larger model already pulled there (e.g. `ollama pull qwen2.5-coder:32b`
  or whatever the target model is — this playbook doesn't prescribe a
  specific model, since that's a hardware/capability decision made at
  GPU-arrival time, not before).

## Steps

1. **Point `OLLAMA_URL` at the GPU host.** Every service that talks to
   Ollama reads this from its own environment
   (`services/agents/agents/reasoning_engine/ollama_adapter.py`,
   `services/knowledge/`'s embedding backend) — no code path hardcodes
   `localhost:11434`. Set it once, per service, in whatever the real
   deployment's env-var mechanism is (`docker-compose.yml`'s `environment:`
   blocks, or a systemd unit's `Environment=`).

2. **Flip the default model in config**, not in code:
   `services/platform-spine/platform_spine/config_manager/files/reasoning_engine.yaml`
   — `default_local_model: <new-model-tag>`. `model_router.py`'s
   `has_model()` pre-flight (Phase 23) already checks the real, live tag
   list before ever routing to it, so a typo here fails closed with a
   real error, not a silent fallback to the old model.

3. **Confirm the classification ceiling recognizes the new model.**
   `services/assembly/assembly/context_builder/classification.py`'s
   `ceiling_for_model()` (Phase 4/11) grants the `confidential` ceiling
   only to whatever `default_local_model`/`fallback_local_model` name —
   Phase 27 found and fixed a real bug here once already (a stale config
   value silently downgraded the ceiling); after step 2, re-verify with
   a real request through `services/platform-spine/platform_spine/gateway/openai_shim.py`'s
   `/v1/chat/completions` carrying `internal`-classified content and
   confirm it's still allowed, not silently refused.

4. **Phase 27's endpoint becomes primary for IDE model traffic.** Once
   the larger model is live and the ceiling check passes, any IDE
   already using `/v1/chat/completions` (Phase 27) picks up the new
   model automatically — no IDE-side reconfiguration beyond what
   `docs/ide-recipes/` already documents, since the endpoint URL and
   auth don't change, only what's behind them.

5. **Embeddings stay unchanged.** `EMBEDDING_BACKEND=ollama` (Phase 25)
   already runs `nomic-embed-text` independently of the reasoning
   model's own tag — a GPU upgrade to the reasoning model doesn't
   require re-pulling or reconfiguring embeddings, and doesn't require
   re-ingesting/reindexing existing documents (only an embedding-model
   *change* would, which this playbook doesn't cover).

6. **Re-run the Phase 25 before/after measurement**, if this GPU-day
   swap also changes the coder model specifically — Phase 25 found
   `qwen2.5-coder:7b` was reproducibly less reliable at this system's
   structured-output contract despite better raw code; a larger model on
   real GPU hardware should be re-measured against the same fixed query
   set (`docs/aios-architecture-and-phases.md#phase-25-model-retrieval-quality`)
   before being trusted as the new default for the AGENTIC pipeline, not
   just the raw chat-completions path.

## Rollback

Every step above is a config value, not a migration — reverting
`OLLAMA_URL` and `default_local_model`/`fallback_local_model` to their
prior values and restarting the affected services (`agents`,
`assembly`, `platform-spine`) returns the system to its pre-GPU-day
state exactly, with no data model change to undo.
