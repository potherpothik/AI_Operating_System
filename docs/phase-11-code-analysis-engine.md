# Phase 11 — Structural Code Understanding
### Code Analysis Engine

---

## 0. Priority Decision: Why This Phase Is Eleventh

**Why it exists here:** Phase 10 explicitly surfaced Django Agent's constraint — it operates on documentation alone because no structural code understanding exists yet. Closing that gap now, before the business agents batch, follows the same discipline Phase 9 established: fix a concretely-motivated limitation in what already exists before adding more surface area. It's scoped as its own phase, not folded into Phase 10, because it's genuinely different work — static analysis tooling, not agent configuration — and because its confidentiality design deserves the same dedicated attention database write execution got in Phase 7, given source code is arguably the single most sensitive content type named anywhere in the mandate.

**Alternatives considered**
- *Skip Code Analysis Engine, accept Django Agent's documentation-only limitation permanently* — rejected. The mandate names this module explicitly, and "understand business logic through documentation, structured knowledge, APIs, and tools" means the system shouldn't depend *entirely* on source code — not that code should be invisible to it. Structural understanding is squarely in scope.
- *Ingest raw source directly into Vector Search like any other document, relying on Security Layer's classification filter alone to gate access* — rejected. This is exactly the shortcut the mandate's opening assumption — *"source code is highly confidential... never send source code to external APIs unless explicitly approved"* — warns against. Collapsing structural knowledge and raw source into one undifferentiated tier makes that rule far harder to enforce correctly than a genuine two-tier design does.
- *Build Code Review Agent alongside it, since it's the obvious first consumer* — reasonable, and likely the phase right after this one, but deferred so this phase's full attention goes to getting the structural/raw-source split right — the part of this work that's actually load-bearing for the confidentiality mandate.

**Trade-offs:** no new agent ships this phase, so there's no immediately visible new capability — the payoff is Django Agent quietly getting more capable rather than a new named agent appearing. Accepted; the same trade Phase 3 and Phase 9 already made — infrastructure phases pay off through the agents built on them, not their own visible output.

**Security implications:** the two-tier structural/raw-source split *is* this phase's security design — arguably the most direct implementation yet of the mandate's very first stated assumption.

**Performance implications:** incremental, on-commit analysis (versus full re-scans every time) keeps this from becoming an expensive, blocking step in Git Manager's commit flow. Full scans are reserved for initial repo onboarding or periodic drift-correction.

**Future scalability:** reuses the same two-output-path pattern ERP Knowledge Engine established in Phase 9 — chunked semantic content plus a structured graph query — rather than inventing something new. Evidence that pattern generalizes beyond ERP schema to any structured-knowledge source.

**Estimated complexity:** Medium-high. Static analysis correctness, especially call-graph accuracy across a real codebase, is genuinely hard to get fully right — scoping this first version to structural metadata and docstrings rather than deep semantic code understanding keeps it tractable.

---

## 1. Code Analysis Engine

**Responsibilities**
- Static analysis extracting structured metadata: symbol tables (function/class signatures), call graphs and import/dependency relationships, docstrings and inline comments — explicitly named as a legitimate knowledge layer in the mandate's own source list — and test-coverage mapping useful to Testing Agent (Phase 10)
- **Deliberately does not ingest raw function or class bodies into Vector Search by default.** Two-tier output instead:
  - *Structural tier* (default): signatures, docstrings, comments, module organization, call graph — classified `internal`, freely retrievable via Vector Search like any other Phase 9 content
  - *Raw-source tier*: actual function/class bodies — classified `confidential` by default, reachable only through an explicit, approval-gated request, never auto-ingested anywhere
- Incremental analysis triggered on commit (via Git Manager, Phase 6) — re-analyzes only changed files rather than the whole repository on every change
- Pluggable, language-aware parsing (Python first, given the stack; extensible to JS/TS and Odoo XML views)
- Feeds structural knowledge to Vector Search the same way Documentation Engine does; feeds the call graph to a structured query endpoint, mirroring ERP Knowledge Engine's `/graph` pattern from Phase 9

**Inputs:** repository reference (via Git Manager, read-only); trigger: `on_commit` (incremental) or `full_scan`

**Outputs:** structural records → `Vector Search.ingest()`; call graph → structured graph store; raw source → gated behind an approval check, never auto-published

**APIs**

| Endpoint | Purpose |
|---|---|
| `POST /code-analysis/scan` | Trigger full or incremental analysis |
| `GET /code-analysis/symbol/{ref}` | Structural info for a function/class/module — signature, docstring, callers/callees. The safe, non-confidential default tier |
| `GET /code-analysis/graph` | Call graph / dependency graph query |
| `POST /code-analysis/raw-source-request` | Explicit, approval-gated request for an actual function/class body |

**Failure handling:** a parse failure on an individual file is logged and the file skipped, not treated as a whole-scan failure — but it's surfaced as a visible gap, matching Documentation Engine and Vector Search's own ingestion philosophy. A raw-source request without a valid, matching approval reference is rejected outright — the same structural precondition Database Connector applies to writes in Phase 7.

**Logging:** every scan logged with file count, symbols extracted, and failures. Every raw-source request logged in full — which files, which agent, which approval — since this is the concrete mechanism behind the mandate's single most emphasized confidentiality rule.

**Security:** raw-source requests re-verify the target model is local-only unless a human has explicitly approved a specific external release, reusing Context Builder's model-isolation mechanism (Phase 4) at its strictest, since raw source is the highest-sensitivity content type in the system. Even the structural tier is classified `internal`, not public — a function signature can still leak proprietary algorithm shape or business logic without a body attached, so structure isn't assumed safe by default either.

**Future extension points:** security-focused static analysis (obvious vulnerability patterns) as a separate future effort, not full SAST tooling in this phase; cross-repository call graphs once more than one repo is analyzed; feeding a future Code Review Agent as its primary knowledge source, mirroring how ERP Knowledge Engine is positioned to feed a future Cutlist/Calculation Agent.

---

## 2. How It Fits In

```
Git Manager (Phase 6): commit lands / repo scan triggered
        │
        ▼
Code Analysis Engine.scan(repo_ref, mode=incremental|full)
        ├── structural knowledge (signatures, docstrings, comments)
        │        └── classify internal ──► Vector Search.ingest(...)                  [Phase 3]
        ├── call graph / dependency data ──► structured graph store
        └── raw function/class bodies ──► classified confidential, NOT auto-ingested

Raw-source request path (e.g. Django Agent needing real code detail):
Django Agent → raw-source-request(files, reason)
        ▼
Security Layer.authorize() → classification=confidential, requires_approval           [Phase 1]
        ▼
Human Approval Layer.request(...) — human approves, scoped to specific files/task      [Phase 1]
        ▼
Code Analysis Engine returns raw source, tagged confidential in Context Builder,
which re-verifies target_model is local-only before including it                       [Phase 4]
```

---

## 3. Minimal Data Model for This Phase

```sql
code_symbol (
  id, repo, file_path, symbol_type,     -- function | class | module
  name, signature, docstring, classification, last_analyzed_commit
)
call_edge (
  id, caller_symbol_id, callee_symbol_id, repo, last_seen_commit
)

raw_source_request (
  id, task_id, requesting_capability, files[], reason,
  approved_by, approved_at, expires_at
)

analysis_run (
  id, repo, mode, files_analyzed, files_failed, started_at, completed_at
)
```

---

## 4. Folder Structure for This Phase

```
knowledge_pipelines/
└── code_analysis_engine/
    ├── api.py
    ├── parsers/                   # python.py, javascript.py, xml.py (Odoo views), ...
    ├── symbol_extractor.py          # signatures, docstrings, comments
    ├── call_graph.py                 # caller/callee relationships
    ├── classifier.py                  # structural=internal default; bodies=confidential default
    ├── raw_source_gate.py              # approval-gated access to actual bodies
    └── store.py
```

---

## 5. Explicitly Out of Scope for This Phase

No automated vulnerability/SAST scanning — a separate future effort. No cross-repository call graph — single-repo analysis first. Code Review Agent, its natural first consumer, is not built this phase so full attention stays on the structural/raw-source split itself.

---

## Next

Phase 12: the business agents — Costing, Inventory, Accounting, Manufacturing, Sales, Project Management — the batch flagged as deferred back in Phase 10, now with real ERP knowledge (Phase 9) to draw on. Code Review Agent, Reverse Engineering Agent, and Architecture Agent — the natural consumers of this phase's structural code knowledge — follow after.
