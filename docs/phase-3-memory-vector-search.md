# Phase 3 — Knowledge Substrate
### Memory Manager · Vector Search

---

## 0. Priority Decision: Why This Phase Is Third

**Why it exists here:** Context Builder (Phase 4) and every agent (Phase 5+) need something to retrieve from. Building an agent before this exists means either hardcoding context — defeating the mandate's own principle that *"the AI should understand business logic through documentation, structured knowledge, APIs, and tools — not by memorizing the entire source code"* — or building Context Builder against a stub that later needs replacing. Memory Manager and Vector Search are paired here because they're the same problem from two angles: Memory Manager owns typed, structured records (preferences, decisions, task state); Vector Search owns unstructured document retrieval. Context Builder is the module that blends both into what an agent actually sees, so both need to exist first.

**Alternatives considered**
- *Context Builder / Prompt Builder first, with memory and retrieval stubbed* — rejected. Same "stub becomes permanent" risk as earlier phases, and Context Builder's whole job is knowing how to blend memory with retrieval — designing it before either exists means designing it against guesses.
- *Split into two separate phases* — reasonable, but rejected for now. Knowledge cache (a memory type) is itself vector-backed, and classification enforcement has to be consistent across both — easier to get right designed together, even if implemented by two engineers in parallel.
- *Ship the first agent on Vector Search alone, defer full Memory Manager* — rejected. Business memory, decision history, and user preferences are what make this an AI *operating system* rather than a stateless chatbot with search bolted on — deferring them is the exact shortcut the mandate warns against.

**Trade-offs:** this is the broadest phase yet — ten memory types plus a retrieval engine, real scope-creep risk. Mitigated by explicitly excluding Documentation Engine / ERP Knowledge Engine / Code Analysis Engine (the domain-specific pipelines that *produce* content) — this phase builds only the substrate they'll ingest into.

**Security implications:** memory becomes a second place, alongside Task Manager, where business-sensitive content is persisted. Vector Search's classification filtering is the first point where retrieval could leak confidential content into a lower-privileged agent's context — so it gets the strictest treatment in this phase.

**Performance implications:** vector queries are the first potentially-slow operation in the system. Chunking strategy and default `top_k` matter for keeping Context Builder responsive later. A local-only embedding model makes latency a function of local hardware, not network — a deliberate, predictable offline-first trade.

**Future scalability:** starting on pgvector (Postgres is already in the stack) keeps ops simple now; the ingestion/query contract is designed so swapping to a dedicated vector DB later doesn't change any caller's code.

**Estimated complexity:** Medium-high. First phase with a real ML component (embedding model), and the first with ten distinct retention policies to get right — legitimately its own phase, not foldable into Phase 2 or deferred into agent work.

---

## 1. Memory Manager

**Responsibilities**
- Implements each required memory type with its own retention rule:

| Type | Retention rule |
|---|---|
| Short-term | Cleared on task completion or idle timeout (~30 min) |
| Working | Lives for task duration; promoted to decision history on completion if relevant, else discarded |
| Long-term | Indefinite, versioned — superseded, not silently overwritten |
| Project memory | Lives while the project is active; archived (not deleted) on close |
| Business memory | Indefinite, versioned, changes require Human Approval Layer sign-off |
| User preferences | Indefinite per user; user can view/edit/delete their own |
| Decision history | Indefinite, append-only — like ADRs, only ever superseded |
| Architecture history | Indefinite, versioned, correlated to git commits/tags |
| Conversation history | Configurable per compliance policy (default 90 days unless flagged decision-relevant) |
| Knowledge cache | Cached retrieval/summaries, invalidated when the source document changes, not just on a timer |

- Uniform read/write API regardless of the underlying store per type
- Routes every write through Security Layer classification before persisting
- Namespaces memory by project so recall can't leak across unrelated engagements

**Inputs:** `write{memory_type, namespace, project_id, key, value, classification, actor}`; `read/query{memory_type, namespace, query_or_key}`

**Outputs:** memory records; retention-triggered eviction/archival events → Audit Logger; supersede events for versioned types

**APIs**

| Endpoint | Purpose |
|---|---|
| `POST /memory/{type}/write` | Write a record |
| `GET /memory/{type}/read` | Direct key read |
| `POST /memory/{type}/query` | Semantic query (types backed by vector search) |
| `DELETE /memory/{type}/{key}` | Subject to retention rule — e.g. preferences are hard-deletable, decision history is not |
| `GET /memory/{type}/retention-policy` | Introspect the active policy for a type |

**Failure handling:** writes to durable types (long-term, business, decision/architecture history) are synchronous — a failed write must surface to the caller, never silently drop a decision record. Short-term/working memory failures degrade to "context unavailable" rather than blocking.

**Logging:** every write to project/business/decision/architecture memory is logged to Audit Logger — these are the types where a wrong or malicious write causes real harm. High-volume short-term/working writes are access-controlled but not individually audit-logged.

**Security:** classification is enforced at read time as well as write time — a query can't return source-code-classified content to a caller who isn't cleared for it, no matter what it asks for. Encrypted at rest for all durable types.

**Future extension points:** pluggable backend per type (Postgres + a Redis-like cache to start); background summarization/compaction jobs for aging conversation history; cross-project memory sharing, explicitly approval-gated, for patterns that generalize across engagements.

---

## 2. Vector Search

**Responsibilities**
- Generic embedding, indexing, and semantic retrieval — source-agnostic, so future Documentation Engine / ERP Knowledge Engine / Code Analysis Engine just call its ingestion API instead of each building their own index
- Chunking for long documents, so retrieval returns focused spans, not whole files
- Hybrid retrieval: semantic similarity plus metadata filter (project, classification ceiling, doc type) — pure semantic search is too loose for a system that has to respect classification boundaries
- Local-only embedding model by default, pluggable — never assumes an external embedding API is reachable
- Reindex on source-document change, feeding Memory Manager's knowledge-cache invalidation

**Inputs:** `ingest(document, metadata={source, classification, project_id, doc_type, version})`; `query(text, filters={project_id, classification_ceiling, doc_type}, top_k)`

**Outputs:** ingestion confirmation + `doc_id`; ranked `{chunk, score, source_doc_id, metadata}` list

**APIs**

| Endpoint | Purpose |
|---|---|
| `POST /vector/ingest` | Chunk, embed, and index a document |
| `POST /vector/query` | Semantic + filtered retrieval |
| `DELETE /vector/{doc_id}` | Remove a document and cascade to its chunks |
| `POST /vector/reindex/{doc_id}` | Re-embed on source update |
| `GET /vector/stats` | Index size, per-project breakdown — feeds the future Metrics Dashboard |

**Failure handling:** failed ingestion retries with backoff and surfaces explicitly — an agent believing a document is indexed when it isn't is worse than a visible gap. Query failures fail closed to "no results," never to stale or wrong matches; callers must handle a genuinely empty result rather than assume search always succeeds.

**Logging:** ingestion events (doc_id, source, classification) logged fully. Queries are logged at a lighter level by default (query hash, filters, result count) to avoid the audit log becoming its own sensitive-data store — full query text is logged only for high-classification queries.

**Security:** the classification filter runs *inside* the query itself, server-side — a caller without clearance for confidential content cannot get confidential chunks back; it isn't a post-filter the caller could bypass. Runs on a fully local embedding model, so document content never leaves the network boundary just to be embedded.

**Future extension points:** swap pgvector for a dedicated vector DB (Qdrant/Milvus) if scale demands it, without changing the ingestion/query contract; pluggable embedding model; multi-vector/late-interaction retrieval (ColBERT-style) if simple dense retrieval proves insufficient for code-heavy content.

---

## 3. How the Two Interact

```
Write / ingest path:
Caller (Task Manager, future agent)
   → Memory Manager.write(type, value, classification)
        → Security Layer.classify() + .authorize()             [Phase 1]
        → persist to type-appropriate store
        → Audit Logger (project/business/decision/architecture types)   [Phase 1]

   → Vector Search.ingest(document, metadata)
        → chunk → embed (local model) → store in pgvector
        → Audit Logger (ingestion event)                        [Phase 1]

Query path (future Context Builder is the caller):
   → Memory Manager.query(type, query)  ── classification-filtered by type-appropriate store
   → Vector Search.query(text, filters incl. classification_ceiling)
        → embed query → similarity search WHERE classification <= caller's ceiling
        → ranked chunks returned
```

---

## 4. Minimal Data Model for This Phase

```sql
-- structured memory
memory_record (
  id, memory_type, namespace, project_id, key, value_json,
  classification, created_by, created_at, superseded_by, ttl_expires_at
)

-- append-only, never updated in place
decision_record (
  id, project_id, title, rationale, alternatives_considered,
  decided_by, decided_at, supersedes_id
)

-- vector store (pgvector)
document (id, source, doc_type, project_id, classification, version, ingested_at)
chunk (id, document_id, content, embedding VECTOR(dim), chunk_index)
```

---

## 5. Folder Structure for This Phase

```
knowledge/
├── memory_manager/
│   ├── api.py
│   ├── types/                 # short_term.py, working.py, decision_history.py, ...
│   ├── retention.py            # TTL / eviction / archival rules per type
│   └── store.py
└── vector_search/
    ├── api.py
    ├── chunking.py
    ├── embedding.py            # local embedding model interface (Ollama-compatible)
    ├── index.py                 # pgvector-backed index
    └── retention.py             # reindex-on-source-change logic
```

---

## 6. Explicitly Out of Scope for This Phase

Documentation Engine, ERP Knowledge Engine, and Code Analysis Engine — the domain-specific pipelines that will call `vector.ingest()` with real content — are not built here; this phase only builds the substrate they plug into. Context Builder and Prompt Builder (Phase 4) are the consumers that turn memory + retrieval into what an agent sees. No agents yet.

---

## Next

Phase 4: Context Builder + Prompt Builder — the first module to actually assemble what an agent sees, drawing on this phase's memory and retrieval, immediately ahead of the first real agent in Phase 5.
