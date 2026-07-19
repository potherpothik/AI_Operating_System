# Phase 9 — Documentation Engine & ERP Knowledge Engine (working implementation)

Real, tested code. Every agent built so far — Odoo Agent (Phase 5),
Database Agent (Phase 7) — and Planner (Phase 8) reasoning about them,
has been operating against placeholder cached schema and business
memory. This phase closes that gap: real document parsing feeding real
content into Vector Search, and real ERP schema introspection feeding
both Vector Search and business memory. No changes needed anywhere
upstream — Context Builder, Prompt Builder, Reasoning Engine, and every
agent were already built against Memory Manager/Vector Search's generic
interface (Phase 3), so this phase slots in underneath them.

## Run it

```bash
pip install -r requirements.txt
export SECURITY_LAYER_URL=http://localhost:8000
export KNOWLEDGE_URL=http://localhost:8003        # Vector Search + Memory Manager
export DATABASE_CONNECTOR_URL=http://localhost:8007  # ERP Knowledge Engine's schema source
uvicorn main:app --port 8009
```

## Test it

```bash
pytest tests/test_parsers.py -q   # no live dependencies

SECURITY_LAYER_URL=http://localhost:8000 KNOWLEDGE_URL=http://localhost:8003 \
DATABASE_CONNECTOR_URL=http://localhost:8007 \
DEMO_ERP_DATABASE_URL=postgresql://user:pass@host:5432/demo_erp \
pytest tests/ -v   # full suite against the live stack
```

27 tests, all passing against real Postgres (genuine `TIMESTAMPTZ`
columns, confirmed via direct schema inspection, under a non-UTC
session). Real parsing (a genuinely generated PDF via `reportlab`, a
real `.docx` via `python-docx`, real markdown/YAML/JSON) landing in
real, independently-queryable Vector Search content — no mocks.

## What's real

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

## Next

Phase 10: round out the core engineering-platform agents — Django Agent,
DevOps Agent, Docker Agent, Testing Agent — as a batch. The pattern
(capability.yaml + template + Reasoning Engine + Planner routing + real
ingested knowledge) is now proven and properly resourced enough to scale
out agent coverage rather than build more shared infrastructure.
