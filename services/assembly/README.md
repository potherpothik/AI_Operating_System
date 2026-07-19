# Phase 4 — Context Builder & Prompt Builder (working implementation)

Real, tested code. This is the first phase with a genuine four-service
dependency chain: it calls `governance` (classify/audit/approval),
`platform-spine` (config, to know which models are local), and `knowledge`
(memory + vector search) — all over real HTTP.

## Run it

```bash
pip install -r requirements.txt
# governance, platform-spine, and knowledge must already be running —
# see each one's own README. Then:
export SECURITY_LAYER_URL=http://localhost:8000
export PLATFORM_URL=http://localhost:8002
export KNOWLEDGE_URL=http://localhost:8003
uvicorn main:app --port 8004
```

## Test it

```bash
pytest tests/ -q   # budget + schema validation only, no dependencies

PHASE1_PATH=/path/to/governance \
PHASE2_PATH=/path/to/platform-spine \
PHASE3_PATH=/path/to/knowledge \
pytest tests/ -v    # full suite, all three auto-started if not already running
```

26 tests. All passed on the first full run against all three real
dependent services — the earlier phases' lessons (timezone-aware columns,
conftest respecting `DATABASE_URL`, fail-closed on unreachable services)
held up rather than needing to be rediscovered. One real bug *was* found
by the live end-to-end test, not the test suite: the shared refuse/
delegate/approval instruction fragment showed `{{` and `}}` instead of
`{` and `}` in its JSON schema example, because it's substituted as a
`.format()` *value*, which never gets a second pass to unescape braces —
only visible by actually rendering a prompt and reading it, which is
exactly why the live smoke test matters alongside the unit tests. Fixed,
and locked in as a permanent regression test
(`test_rendered_json_schema_example_uses_single_braces_not_doubled`).

## What's real

- **Context Builder**: pulls from real Memory Manager and Vector Search,
  derives a classification ceiling from Config Manager's actual
  `external_model_allowed`/local-model settings (confirmed: an
  unrecognized external model gets `public`, a configured local model
  gets `confidential`), enforces it server-side before retrieval — not a
  post-filter — dedupes overlapping hits, respects human-pinned facts
  over budget truncation, and logs a reference (not full content) to
  governance's central audit trail.
- **Prompt Builder**: template registration is genuinely approval-gated
  through governance (same pattern as Phase 3's `business_memory`,
  confirmed live: a rejected template never becomes active). Every
  context item is structurally wrapped in `<untrusted_context>` tags —
  not a convention a template author has to remember, the render
  function does it unconditionally. Refuses outright rather than
  silently truncating an over-budget prompt.

- **`GET /context/model-ceiling` (Phase 11)**: exposes
  `classification.ceiling_for_model()` over HTTP so a service outside
  this one — Code Analysis Engine's `raw_source_gate.py` — can
  re-verify a target model is local-only before releasing confidential
  raw source that never routes through Vector Search/Context Builder at
  all. A real bug caught building it: the route was originally
  registered *after* `GET /context/{context_id}`, so FastAPI matched
  the literal string `"model-ceiling"` as a `context_id` and returned a
  plain 404 instead of ever reaching the new handler — invisible to a
  direct function-call test, only caught by an actual HTTP request.
  Fixed by moving it earlier in the router; regression-tested with
  `TestClient` specifically because a direct function call wouldn't
  have caught this class of bug (`test_model_ceiling_reachable_over_real_http_routing`).

## What's a stub or simplified

- **Token budgeting is word-count based, not exact token counting.** A
  real tokenizer needs vocabulary files this sandbox can't download (same
  constraint that shaped Phase 3's embedding choice). Swappable in
  `budget.py` without touching anything else's contract.
- **Classification ceiling logic is a simple local/external check**
  against Config Manager's settings, not yet wired to a full model
  registry — reasonable for two models (`qwen-coder`, `deepseek-coder`
  per the stack), will want a real registry once more models are in play.

## Next

Phase 5 (Reasoning Engine, Odoo Agent) is the first phase that actually
calls a model with what Context Builder and Prompt Builder assemble here
— completing the loop this phase only builds half of.
