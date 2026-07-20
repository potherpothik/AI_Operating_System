# Phase 3 — Knowledge Substrate (working implementation)

Memory Manager (all 10 memory types) and Vector Search — real, tested code.
Depends on Phase 1 for classification and, for `business_memory` writes, real
approval. Doesn't depend on Phase 2 at all.

## Run it

```bash
pip install -r requirements.txt

# Phase 1 must be running — Memory Manager calls it for classification and
# (for business_memory) approval.
export SECURITY_LAYER_URL="http://localhost:8000"
uvicorn main:app --port 8003
```

## Test it

```bash
pytest tests/ -q                                          # unit tests only
PHASE1_PATH=/path/to/phase1-governance pytest tests/ -v    # full suite, incl. real approval flow
```

23 tests. Confirmed live, not just under the test harness: real pgvector
similarity search returning the right document for a semantically related
query, the classification heuristic catching an embedded `api_key:` pattern
and correctly marking it confidential, and a `business_memory` write
creating a genuine pending approval against a live Phase 1 instance —
invisible until actually approved, confirmed invisible again if rejected.

## The embedding model — read this before trusting search quality

This sandbox has no route to HuggingFace Hub (confirmed: 403 Forbidden) or
to a live Ollama instance, so a real transformer embedding model couldn't be
downloaded or tested here. Two implementations exist
(`knowledge/vector_search/embedding.py`):

- **`HashingEmbedding`** (default) — fully local, deterministic, real feature
  hashing, not a stub. Every test above ran against it and it's genuinely
  exercised end to end. It captures **lexical overlap, not semantic
  similarity** — it has no notion that "car" and "automobile" are related.
  Fine for exact/near-exact term matches, meaningfully weaker for
  paraphrased queries than a real embedding model would be.
- **`OllamaEmbedding`** — written to Ollama's real `/api/embeddings`
  contract, but **not live-tested against an actual Ollama instance** —
  there's no network route to one from here. Point `EMBEDDING_BACKEND=ollama`
  and `OLLAMA_URL` at your real instance and verify it before relying on it;
  don't assume it's exercised the way `HashingEmbedding` has been.

Swapping between them is one environment variable — nothing else in Vector
Search's ingest/query contract changes either way, since both implement the
same `EmbeddingModel` interface.

## Postgres — real pgvector, not a stand-in

```bash
export DATABASE_URL="postgresql://user:pass@host:5432/knowledge"
```

`knowledge/db.py` runs `CREATE EXTENSION IF NOT EXISTS vector` on startup.
The `embedding` column is a genuine pgvector `VECTOR(512)` type on Postgres
(confirmed directly via `\d chunk`), with similarity search using pgvector's
real `cosine_distance` operator — not emulated. SQLite (local dev only)
falls back to a JSON-encoded column with Python-computed cosine similarity —
a linear scan, correct but not built for scale, which is what the Postgres
path is for. Tested against both, including under a deliberately non-UTC
Postgres session (the same class of bug found in Phase 1 — every timestamp
column here uses `DateTime(timezone=True)` from the start).

## Two small additions to Phase 1

This phase needed two endpoints Phase 1 didn't have yet — added there, not
here, and re-verified (17 tests still passing on both backends):

- `POST /security/classify` — a real heuristic classifier (regex-based
  secret/PII detection), not a stub. Returns the more restrictive of the
  caller's declared classification and whatever the heuristic detects.
- `GET /approval/{id}` — lets a caller check one specific request's status,
  rather than only listing everything pending.

If you already have Phase 1 deployed, pull the updated
`governance/security/` and `governance/approval/api.py` files.

## Phase 13 addition

`GET /vector/stats` now also returns `by_classification` (alongside the
existing `by_project`) — Observability's Metrics Dashboard classification-
distribution category, the one category with an actual classification
dimension on the underlying rows.

## What's a stub or simplified

- `query_text()` for non-`knowledge_cache` memory types is substring
  matching, not semantic search — `knowledge_cache` itself delegates to
  real Vector Search, per the design.
- `working` memory's retention is TTL-only for now (4-hour backstop) —
  clearing it on actual task completion needs Reasoning Engine (Phase 5),
  which doesn't exist yet.

## Next

Phase 4 (Context Builder, Prompt Builder) is the first real consumer of
both modules built here — it queries Memory Manager and Vector Search to
assemble what an agent actually sees.
