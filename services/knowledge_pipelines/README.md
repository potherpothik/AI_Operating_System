# Phase 9/11 — Documentation, ERP Knowledge & Code Analysis Engines (working implementation)

Real, tested code. Every agent built so far — Odoo Agent (Phase 5),
Database Agent (Phase 7) — and Planner (Phase 8) reasoning about them,
has been operating against placeholder cached schema and business
memory. Phase 9 closed that gap for documents and ERP schema: real
document parsing feeding real content into Vector Search, and real ERP
schema introspection feeding both Vector Search and business memory. No
changes needed anywhere upstream — Context Builder, Prompt Builder,
Reasoning Engine, and every agent were already built against Memory
Manager/Vector Search's generic interface (Phase 3), so Phase 9 slotted
in underneath them. Phase 11 closes the analogous gap for source code:
Django Agent (Phase 10) has been reasoning about Django app structure
from documentation alone. Code Analysis Engine adds real static
analysis via Python's own `ast` module, with a genuine two-tier split —
structural metadata (signatures, docstrings, call graph) flows into
Vector Search like any other Phase 9 content, but actual function/class
bodies are never auto-ingested anywhere, reachable only through an
explicit, approval-gated request that re-verifies the requesting model
is local-only at release time, not just at request time.

## Run it

```bash
pip install -r requirements.txt
export SECURITY_LAYER_URL=http://localhost:8000
export KNOWLEDGE_URL=http://localhost:8003        # Vector Search + Memory Manager
export DATABASE_CONNECTOR_URL=http://localhost:8007  # ERP Knowledge Engine's schema source
export ASSEMBLY_URL=http://localhost:8004  # Code Analysis Engine's raw-source-request model-isolation re-check (Phase 11)
uvicorn main:app --port 8009
```

Code Analysis Engine's `POST /code-analysis/scan` takes a real local
directory (`repo`), the same "real working_dir on disk" convention
Phase 6/7's `PROPOSAL_REPO_PATH` established — not a remote URL Git
Manager clones on its behalf. To get the `on_commit` trigger genuinely
firing (Phase 11 doc, Section 1), also point Phase 6's execution service
at this one:

```bash
# in services/execution's own terminal
export CODE_ANALYSIS_URL=http://localhost:8009
```

Without it, `git/commit` still succeeds — the trigger is best-effort and
never blocks or fails a real commit, it's just skipped (confirmed by
`test_code_analysis_trigger_is_a_real_no_op_when_unconfigured` in
`services/execution/tests/test_git_manager.py`).

## Test it

```bash
pytest tests/test_parsers.py tests/test_code_analysis_parser.py -q   # no live dependencies

SECURITY_LAYER_URL=http://localhost:8000 KNOWLEDGE_URL=http://localhost:8003 \
DATABASE_CONNECTOR_URL=http://localhost:8007 ASSEMBLY_URL=http://localhost:8004 PLATFORM_URL=http://localhost:8002 \
DEMO_ERP_DATABASE_URL=postgresql://user:pass@host:5432/demo_erp \
pytest tests/ -v   # full suite against the live stack
```

49 tests, all passing against real Postgres (genuine `TIMESTAMPTZ`
columns, confirmed via direct schema inspection, under a non-UTC
session). Real parsing (a genuinely generated PDF via `reportlab`, a
real `.docx` via `python-docx`, real markdown/YAML/JSON, and real Python
source via `ast`) landing in real, independently-queryable Vector Search
content — no mocks.

## What's real

- **Phase 16 addition:** `POST /docs/ingest` and `GET /code-analysis/graph`
  are now genuinely driven by an agent for the first time — Reverse
  Engineering Agent's approved `propose_documentation_draft` calls
  `/docs/ingest` on the exact same file Git Manager just committed
  (`services/agents/README.md`'s Phase 16 section), and Code Review
  Agent's `review.check_callers` tool call reads `/graph` to resolve a
  changed symbol's real callers. No code changed in this service for
  either — both endpoints already existed since Phase 9/11, just never
  had a real caller before.
- **Phase 13 addition:** `GET /erp-knowledge/snapshots` — one row per
  `target_db` ever synced, whatever its latest status. Observability's
  Health Monitor stale-ERP-knowledge check needs this to discover
  staleness across every synced target, not just one it already knows
  to ask `GET /graph?target_db=...` about.
- **All four document parsers are genuinely tested, not stubs.** PyPI
  access worked in this environment (unlike Phase 3's HuggingFace
  constraint), so `pdf.py` (pypdf) and `docx.py` (python-docx) are real,
  confirmed by generating actual PDF/DOCX files with real text content
  and parsing them back — not blank pages or mocked extraction.
- **Unparseable documents fail explicitly, never silently** — confirmed
  live: a corrupted "PDF" that's just garbage bytes raises a real 422
  with the parser's actual error, and the failure is recorded in
  `doc_ingestion_log`, not dropped.
- **Classification defaults conservative and stays that way until a
  real human correction is approved** — confirmed live: an unclassified
  document lands as `confidential` (the most restrictive tier), and
  `/docs/classify-override` requires a genuine governance approval
  before the correction actually reindexes the content under the new
  classification (Vector Search has no in-place classification update,
  so this really does delete the old document and re-ingest — confirmed
  by attempting to reindex the deleted document and getting Vector
  Search's real 404).
- **The "watch" mechanism genuinely detects real file changes**: content
  is hashed at ingest time, and `/docs/sources/{id}/check` only
  reindexes when the file's current content hash actually differs —
  confirmed live with an unmodified file (no reindex) and then a real
  edit (reindexed, and the new content is immediately queryable).
- **ERP Knowledge Engine's schema sync is real, not mocked**: pulls
  directly from Phase 7's Database Connector (which itself was extended
  in this phase to return foreign keys, not just column names — a real
  gap this phase surfaced), against the same seeded `demo_erp` database
  every prior phase's tests use. The structured relationship graph
  reflects a genuine foreign key (`sale_order.partner_id → res_partner`),
  confirmed both directions (`references` and `referenced_by`).
- **A failed schema sync marks that target's knowledge `stale`**, never
  silently continuing to serve a prior sync as current — confirmed live,
  and confirmed that a failure against one target doesn't affect another
  target's already-current snapshot.
- **Human-authored field annotations genuinely fold into the next sync's
  prose** — confirmed live: an annotation's business-meaning text shows
  up as real, independently-queryable content after the next
  `/erp-knowledge/sync` call, without needing any code change to pick it
  up (the sync always re-reads current annotations when generating
  prose).
- **Formula registration is a real, durable, versioned, approval-gated
  write** — routed through Memory Manager's `business_memory` (Phase 3),
  confirmed to come back `pending_approval` with a real approval ID
  every time, per that memory type's retention policy. Re-registering a
  formula under the same name genuinely supersedes the prior version
  rather than silently overwriting it — confirmed both records remain
  independently retrievable with their real `superseded_by` link intact.
  A formula whose name or purpose mentions pricing is confirmed to
  auto-classify `confidential`, not the default `internal`.
- **Code Analysis Engine's Python parsing is real static analysis via
  the standard library's own `ast` module**, not a regex approximation
  or a stub — confirmed against real, genuinely cross-referencing source
  files: real signatures (including type annotations), real docstrings,
  real line numbers, and a real intra-file call graph (`Widget.render`
  calling both `helper` and `self.finalize` resolved as two distinct,
  correct edges).
- **The full Phase 11 loop closes for real, end to end, live** — not
  just unit-tested in isolation: a genuine `git commit` through Phase
  6's real Git Manager fires Code Analysis Engine's incremental scan
  automatically, real symbols and a real call graph land in this
  service's own tables (`last_analyzed_commit` matching the actual
  commit SHA), and the structural prose is independently queryable back
  out of Vector Search — confirmed by committing a real two-function
  file and querying for it afterward, not by reading the code.
- **The raw-source-request approval gate is real, not a status flip**:
  confirmed live end to end — request → real governance approval
  (`POST /approval/{id}/decide`) → fetch → the *exact* bytes on disk
  come back, verified against the real file content directly. Fetching
  before approval returns `pending`, never partial or placeholder
  content. A request approved for a local model but re-checked with a
  non-local `target_model` at fetch time is refused — confirmed live —
  because the model-isolation check re-runs fresh at release time, not
  just once at request time.
- **A real bug this phase caught, not a hypothetical**: `GET
  /context/model-ceiling` (added to `assembly` for this phase's
  raw-source-gate re-check) was originally registered in the router
  *after* `GET /context/{context_id}`, so FastAPI matched the literal
  string `"model-ceiling"` against the `{context_id}` path parameter
  first and returned a plain 404 — invisible to a direct function call,
  only caught by an actual HTTP request through the real route table.
  Fixed by registering the literal-path route first; a permanent
  regression test (`test_model_ceiling_reachable_over_real_http_routing`
  in `services/assembly/tests/test_classification.py`) uses `TestClient`
  specifically so this class of bug can't silently return.

## What's a stub or simplified

- **"Watching" is poll-triggered via `POST /docs/sources/{id}/check`,
  not a continuously-running background daemon.** The Phase 9 doc flags
  change-watching as "the first genuinely continuous background process
  in the system" — building a real long-running watcher thread/asyncio
  loop within this system's otherwise entirely request-triggered
  architecture felt like a bigger, separately-worth-scrutinizing design
  decision than this phase's actual scope called for. A cron job or
  external scheduler hitting this endpoint periodically gets the same
  outcome the doc describes; a genuine in-process daemon is a reasonable
  future extension once there's a concrete reason to need push-based
  latency instead of poll-based.
- **No live Odoo instance exists in this environment** — ERP Knowledge
  Engine syncs against the same seeded Postgres `demo_erp` database
  every phase since 7 has used, via Database Connector's generic schema
  introspection. This is real relational data with a real foreign key,
  but it's not actually Odoo — there's no module-manifest concept to
  introspect, so `module_count` on `erp_schema_snapshot` is a fixed
  placeholder (1), not a genuine Odoo module count. The sync mechanism
  itself (fetch → snapshot → prose → structured graph) is real and would
  work unchanged against a real Odoo-backed Postgres database.
- **No automatic annotation or formula generation** — explicit
  out-of-scope per the Phase 9 doc. A human always writes the
  business-meaning text; nothing in this phase drafts it, including via
  an LLM.
- **`/erp-knowledge/formula/register` isn't in the Phase 9 doc's own API
  table**, which lists only `GET .../formula/{id}` for retrieval — a
  real, necessary gap (something has to let a human register a formula
  in the first place), filled with a reasonably-scoped addition.
- **Call-graph resolution is intra-file only** (Phase 11 doc, Section 0
  names this explicitly: "call-graph accuracy across a real codebase is
  genuinely hard to get fully right... keeps it tractable"). A call from
  one file to a function defined in another file is not recorded as an
  edge — not silently approximated, just genuinely out of scope for this
  first version. `models.py`'s `CallEdge` docstring and `call_graph.py`'s
  own comments both say so explicitly at the point a future reader would
  reasonably assume otherwise.
- **JavaScript/TypeScript and Odoo XML view parsing are named extension
  points, not implemented** — `parsers/javascript.py` and `parsers/xml.py`
  raise `NotImplementedError` (surfaced through the normal
  `UnsupportedFormat` path, not a crash) rather than pretending to parse
  something they can't. Python's built-in `ast` module made Python
  tractable to do for real in this phase; neither JS/TS nor Odoo XML
  views have an equivalent built-in, and both need real, separate work.
- **Raw source bodies are never persisted in this service's own
  database** — `CodeSymbol` stores only the structural tier; an approved
  `raw-source-request` reads the actual file content live from disk at
  fetch time. Deliberate: a second confidential copy sitting in a
  queryable table would undermine the whole point of gating access to it
  in the first place.
- **No cross-repository call graph** — explicit out-of-scope per the
  Phase 11 doc, same as intra-file-only resolution above; single-repo
  analysis first.

## Next

Phase 12: the business agents — Costing, Inventory, Accounting,
Manufacturing, Sales, Project Management — the batch flagged as deferred
back in Phase 10, now with real ERP knowledge (Phase 9) and real code
structure (Phase 11) to draw on. Code Review Agent, Reverse Engineering
Agent, and Architecture Agent — the natural first consumers of this
phase's structural code knowledge — follow after.
