# Phase 9 — Knowledge Ingestion
### Documentation Engine · ERP Knowledge Engine

---

## 0. Priority Decision: Why This Phase Is Ninth

**Why it exists here:** every agent built so far — Odoo Agent (Phase 5), Database Agent (Phase 7) — and Planner (Phase 8) reasoning about them, has been operating against placeholder cached schema and business memory, because the pipelines that actually produce real content were explicitly deferred at every phase since Phase 3. With governance, spine, knowledge substrate, context/prompt assembly, a working agent, code execution, data execution, and routing all proven, the system's biggest remaining gap isn't more infrastructure or more agents — it's that the agents it already has are knowledge-starved. Documentation Engine and ERP Knowledge Engine are paired as the two natural halves of "get real content into Vector Search": generic document-shaped sources, and ERP-structure-aware sources that need schema-level understanding rather than just text parsing.

**Alternatives considered**
- *Keep adding agents (Django Agent, DevOps Agent, ...) before closing the knowledge gap* — rejected. Every new agent built on placeholder memory inherits the exact limitation Odoo Agent and Database Agent already have; better to fix the shared substrate once than let the gap multiply across more agents.
- *Build ERP Knowledge Engine alone, defer generic Documentation Engine* — rejected. Meeting notes, architecture documents, and user manuals are exactly the knowledge layers the mandate names alongside structured ERP data. Skipping them means agents still can't answer "why was this decided" or "what does the manual say," even with perfect schema knowledge.
- *Treat ERP Knowledge Engine's output as just more chunked text for Vector Search, no separate structural query path* — rejected. Questions like "what tables reference this one" or "what's the full approval chain for this workflow" are relational questions semantic similarity search answers poorly. A lightweight structured query path alongside vector retrieval is worth the added surface.

**Trade-offs:** this phase leans heavily on human-authored annotation to be genuinely useful — raw schema introspection tells an agent a column's name, never its business meaning. Accepted as an honest reflection of the real bottleneck: encoding tribal knowledge always needs a human source somewhere; this phase's job is giving that input a durable, versioned home, not pretending it can be automated away entirely.

**Security implications:** Documentation Engine is a significant new entry point for un-vetted, human-authored content — and so a prompt-injection surface at the *source*, not only at Prompt Builder's render step. Its output must consistently preserve "untrusted content" tagging. ERP Knowledge Engine handles what may be the most commercially sensitive content in the system — costing and pricing formulas — so its default classification posture is deliberately conservative.

**Performance implications:** change-watching and live-Odoo-sync are the first genuinely continuous background processes in the system, versus request-triggered work everywhere else — worth scoping their frequency so they don't compete with agent-facing query load on the same databases.

**Future scalability:** routing structured ERP knowledge to both Vector Search (semantic) and Memory Manager's business memory (durable, versioned, approval-gated) — rather than forcing everything through one path — means future knowledge types can pick whichever store fits their actual retrieval and governance needs.

**Estimated complexity:** Medium-high. Documentation Engine's complexity is mostly breadth (many formats, many sources). ERP Knowledge Engine's complexity is genuine depth in one place: correctly modeling Odoo's module/schema semantics and keeping them synchronized with a live, changing instance.

---

## 1. Documentation Engine

**Responsibilities**
- Generic ingestion for document-shaped sources: official docs, markdown files, architecture documents, API documentation, meeting notes, user manuals, historical design-decision documents, and git commit/MR messages as metadata (not code content)
- Format-aware parsing (markdown, plain text, PDF, DOCX, OpenAPI specs, ...), each with its own extraction path to clean text
- Preserves document structure (headings, sections) as metadata, so Vector Search can chunk along natural boundaries and label retrieved chunks with their section context
- Watches registered source locations for changes and triggers reindexing via `Vector Search.reindex` rather than requiring manual re-ingestion
- Assigns classification at ingestion time — from explicit source metadata where available, defaulting to the most restrictive tier when ambiguous
- Recognizes duplicate or superseded versions of the same document rather than indexing all of them as equally current

**Inputs:** `{path_or_url, source_type, doc_type, project_id, explicit_classification?}`; triggered or scheduled watch

**Outputs:** `{clean_text, structure_metadata, classification, doc_type, source_ref}` for Vector Search ingestion; ingestion status

**APIs**

| Endpoint | Purpose |
|---|---|
| `POST /docs/ingest` | Ingest a single document |
| `POST /docs/watch` | Register a source location for change-triggered reindexing |
| `GET /docs/sources` | List registered sources and last-ingested status |
| `POST /docs/classify-override` | Human correction of an auto-assigned classification — approval-gated |

**Failure handling:** unparseable documents surface as an explicit ingestion failure with reason, never a silent skip — the same philosophy Vector Search already applies in Phase 3. Any classification ambiguity defaults conservative; better to under-serve a query than leak content because classification metadata was missing or malformed.

**Logging:** every ingestion, reindex, and classification decision — including auto-assigned defaults — logged to Audit Logger.

**Security:** this module is where un-vetted, human-authored content enters the system, and a prompt-injection surface at the source rather than only at render time. It doesn't need to re-solve injection defense, but it must consistently preserve the "untrusted content" tagging that Security Layer and Prompt Builder already act on — never accidentally strip it.

**Future extension points:** OCR for scanned/image-based documents; multi-language support; ingest-time summarization of very long source documents, complementary to Context Builder's runtime summarization.

---

## 2. ERP Knowledge Engine

**Responsibilities**
- Ingests ERP-structure-aware knowledge that generic parsing can't meaningfully extract: Odoo module metadata, model and field definitions with their *business* meaning (not just column names), database schema and ER relationships (introspected live via Database Connector's read-only schema endpoint), business rules as actually configured in Odoo (workflow states, approval chains, computed-field logic), and engineering/costing formulas specific to the business
- Produces both chunked-prose knowledge for semantic retrieval *and* a structured relationship graph agents can query precisely — a distinct, more exact query mode than Vector Search's similarity search
- Periodically re-syncs from the live Odoo instance rather than ingesting only a point-in-time export, since module metadata drifts as modules are installed and updated
- Routes knowledge to the store that fits it: one-off explanations to Vector Search; durable, versioned business rules to Memory Manager's business memory, which — per Phase 3's retention rule — requires Human Approval Layer sign-off to change

**Inputs:** live Odoo connection via Database Connector's read-only schema path; module manifests; human-authored business-context annotations

**Outputs:** structured knowledge records → `Vector Search.ingest()` and/or `Memory Manager.write(business_memory)`

**APIs**

| Endpoint | Purpose |
|---|---|
| `POST /erp-knowledge/sync` | Resync against the live Odoo instance's current module/schema state |
| `POST /erp-knowledge/annotate` | Human adds business context to a field, rule, or formula |
| `GET /erp-knowledge/graph` | Query the structured ER/module relationship graph directly |
| `GET /erp-knowledge/formula/{id}` | Retrieve a formula with its provenance |

**Failure handling:** a failed sync against the live Odoo instance marks affected knowledge `stale` rather than continuing to serve it as current — inherited directly from Database Connector's own fail-closed schema-read discipline in Phase 7.

**Logging:** every sync, annotation, and formula registration logged to Audit Logger — annotations especially, since they encode business knowledge into the system's source of truth and should be attributable and reviewable if a formula later turns out wrong.

**Security:** engineering and costing formulas default to at least "internal" classification, "confidential" for pricing specifically, unless a human explicitly marks otherwise. Live Odoo sync goes through the same read-only, Security-Layer-authorized path as any other Database Connector read — ERP Knowledge Engine holds no elevated DB privilege of its own.

**Future extension points:** automatic schema-drift detection — a module updated without a corresponding annotation update gets flagged for review rather than silently served against stale context; versioned formulas with retained history, mirroring decision history's append-only pattern; becoming the primary knowledge source for a future Cutlist Optimization Agent or Calculation Agent.

---

## 3. How the Two Interact

```
Documentation Engine
        │
        ├── watch(source) → change detected → parse(format) → classify → structure_metadata
        └── → Vector Search.ingest(clean_text, metadata)                            [Phase 3]

ERP Knowledge Engine
        │
        ├── sync() → Database Connector.schema(...)  [read-only]                     [Phase 7]
        ├── human /annotate → business context attached to schema elements
        ├── one-off knowledge (formula explanation, ER description)
        │        └── → Vector Search.ingest(...)
        └── durable, versioned business rule
                 └── → Memory Manager.write(business_memory, ...)                     [Phase 3]
                          └── Human Approval Layer sign-off required                    [Phase 1]

Downstream, immediately: Odoo Agent, Database Agent, and Planner's queries against
Vector Search and business memory now return real content instead of placeholders —
zero changes needed to Context Builder, Prompt Builder, Reasoning Engine, or the agents
themselves. They were already built against the generic Memory Manager / Vector Search
interface, so this phase slots in without touching anything upstream.
```

---

## 4. Minimal Data Model for This Phase

```sql
doc_source (
  id, source_type, path_or_url, doc_type, project_id,
  watch_enabled, last_ingested_at, last_status
)
doc_ingestion_log (
  id, doc_source_id, document_id, classification_assigned,
  classification_is_default, ts, status
)

erp_schema_snapshot (
  id, synced_at, module_count, model_count, status    -- 'current' | 'stale'
)
erp_field_annotation (
  id, model_name, field_name, business_meaning, annotated_by,
  annotated_at, classification
)
erp_formula (
  id, name, formula_ref, business_purpose, classification,
  defined_by, version, superseded_by
)
```

---

## 5. Folder Structure for This Phase

```
knowledge_pipelines/
├── documentation_engine/
│   ├── api.py
│   ├── parsers/                    # markdown.py, pdf.py, docx.py, openapi.py, ...
│   ├── watcher.py                   # change detection, triggers reindex
│   ├── classifier.py                 # default-conservative classification assignment
│   └── store.py
└── erp_knowledge_engine/
    ├── api.py
    ├── odoo_sync.py                  # module/model/field introspection via Database Connector
    ├── annotations.py                 # human business-context capture
    ├── formulas.py                     # engineering/costing formula registry
    └── graph.py                         # structured ER/module relationship queries
```

---

## 6. Explicitly Out of Scope for This Phase

Code Analysis Engine (parsing actual source code for comments/structure) is deliberately deferred — the mandate prioritizes documentation-driven understanding over source-code dependence, and this phase already covers the highest-value non-code knowledge sources. No automatic annotation generation — a human still writes the business-meaning text; LLM-assisted annotation drafting is a noted future extension, not built now, so the system isn't annotating its own knowledge base without a human checkpoint on exactly the content most likely to be subtly wrong.

---

## Next

Phase 10: round out the core engineering-platform agents — Django Agent, DevOps Agent, Docker Agent, Testing Agent — as a batch. The pattern (capability.yaml + template + Reasoning Engine + Planner routing + real ingested knowledge) is now proven and properly resourced enough to scale out agent coverage rather than build more shared infrastructure.
