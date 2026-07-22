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

31 tests (26 as of Phase 4; Phase 26 adds a version-ordering regression
test, Phase 33 adds 2 for the shared operating-discipline fragment — see
below). All passed on the first full run against all three real
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

- **Phase 26: two real, previously latent template-versioning bugs,
  found only because that phase modified an already-active agent
  template for the first time in this project's history.** First:
  `register_template()`/callers like `ensure_template_registered()` only
  ever checked whether a template was *active*, never whether its
  *body* still matched the file on disk — a changed template would
  silently never take effect. `GET /prompt/templates` now includes
  `body` so a caller can actually detect this. Second, more serious:
  `PromptTemplate.version` is a free-text `String` column, and both
  `register_template()`'s `next_version` calculation and
  `get_active_template()`'s "which version is live" query
  (`prompt_builder/templates.py`) ordered by it lexicographically, where
  `"9" > "10"` — once any agent's template crossed version 9,
  `next_version` would keep recomputing `"10"` forever, and
  `get_active_template()` could serve a stale version-9 body for a live
  render instead of the real, newer version 10. Fixed by ordering on
  `created_at` instead of `version` in both places. Full detail in
  `docs/aios-architecture-and-phases.md` Phase 26, Section 3.

## Phase 33 addition — operating discipline for the local model

`prompt_builder/shared_fragments.py`'s `REFUSE_DELEGATE_APPROVAL_FRAGMENT`
gained a short, structured-output-safe addendum: check the answer once
against the task before finalizing, never state a fact you haven't
verified from context or your own declared capability, and set
`confidence` to genuinely reflect real uncertainty rather than a default
high value. Since every agent's `template.md` already embeds this exact
fragment via `{shared_fragment}` (Phase 4's own original design), this
reaches all 25+ agents' rendered prompts with **zero per-agent template
changes** — the fragment is the single injection point.

Deliberately NOT the full multi-page operating manual this was distilled
from (`.cursor/rules/operating-discipline.mdc`, which governs Claude
Code/Cursor when working ON this repo, where token budget isn't a real
constraint). Phase 25 already found, live and measured, that this
project's local 4B-class model's structured-JSON-output reliability gets
*worse* with more verbose prompting, not better — dumping the whole
manual into every agent call here would fight that finding directly, so
this addendum is a few sentences, not a section-by-section transplant.

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
