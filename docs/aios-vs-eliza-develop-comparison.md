# AIOS vs eliza-develop — Capability Comparison

### Source-grounded comparison for upgrade planning

This document compares **AI Operating System (AIOS)** — this Python FastAPI
orchestration layer — with the local study checkout **`eliza-develop/`**
(elizaOS 2.0.x, TypeScript/Bun). elizaOS is **not** a runtime dependency;
patterns may be borrowed via our services only (see
[`elizaos-borrowed-ideas.md`](elizaos-borrowed-ideas.md)).

**Guiding NFR (yours):** *AIOS owns the workflow; third-party tools are plugins.*
Every “better” judgment below is weighed against that rule, plus privacy-first,
governance-first, and replaceable adapters.

**Honesty baseline**

| Project | What “real” means here |
|---|---|
| **AIOS** | Phases 1–22 built as FastAPI microservices with tests; Phase 19 Compose unbuilt in this environment; Phase 23 Model Router and Phase 24 Control UI designed only |
| **elizaOS** | Mature agent runtime + ~147 plugins + web/desktop/mobile UI; packages largely beta-versioned; OS images bootable but certification/update channels still in progress |

Deep dive on eliza internals: [`eliza-develop-technical-reference.md`](eliza-develop-technical-reference.md).
Requirements fit: [`requirements-alignment-assessment.md`](requirements-alignment-assessment.md).

---

## Headline verdict

| Dimension | Winner | One-line why |
|---|---|---|
| Multi-agent architecture | **Split** | elizaOS for live swarm / ACP coding-agent orchestration; AIOS for governed ERP+coding specialist fleet + Planner graphs |
| Memory | **Split** | elizaOS for typed scopes + hybrid retrieval UX; AIOS for classification-aware, approval-gated enterprise memory types |
| RAG (document ingestion) | **elizaOS** | Production hybrid search, URL/YouTube ingest, chat augmentation; AIOS pipelines real but embeddings default to hashing |
| Plugin system | **elizaOS** (breadth) / **AIOS** (governance) | elizaOS Plugin contract is richer; AIOS plugins are approval-gated capability packages |
| Model-agnostic support | **elizaOS** | OpenAI, Anthropic, Ollama, Gemini, Groq, OpenRouter, xAI, local inference; AIOS is Ollama-only today |
| Tool calling | **Split** | elizaOS for native planner tool loop; AIOS for fail-closed authorize → audit → approve → execute |
| REST API | **Split** | elizaOS unified agent API + WS; AIOS explicit microservice contracts + Gateway task spine |
| Web UI | **elizaOS** | Shipping React app; AIOS Phase 24 designed, not built |
| MCP support | **elizaOS** | Official SDK, stdio/HTTP/SSE, discovery; AIOS is a simplified HTTP invoke stub, not wired into Reasoning Engine |
| Local deployment | **Split** | elizaOS one-command `bun run dev` + PGlite; AIOS Compose topology + live-drilled backup, Docker unverified here |

**Strategic takeaway:** elizaOS is a stronger *general agent product platform*. AIOS is a stronger *governed engineering OS for proprietary ERP/code*. Upgrade AIOS by borrowing elizaOS *patterns*, not by adopting its runtime.

---

## Comparison table (detail)

| Capability | AIOS today | eliza-develop today | Better for *your* vision | Why |
|---|---|---|---|---|
| **Multi-agent architecture** | 23+ domain agents as `capability.yaml` + templates on one Reasoning Engine; Planner + Task Manager; `delegate_to` creates tasks (does not auto-run target); Coding Agent Gateway (Phase 22) structurally refuses unsafe live ACP sessions in this env | `AgentRuntime` per agent; World/Room/Entity; SwarmActivity UI trees; `plugin-agent-orchestrator` spawns OpenCode/Claude Code/Codex via ACP with workspace lifecycle | **AIOS** for ERP specialist fleet + governance ownership; **elizaOS** for polished multi-agent *runtime UX* and live coding-agent spawning | Your NFR says *AIOS owns workflow*. AIOS already owns Planner → Task → authorize → approve. elizaOS owns a richer in-process loop and live sub-agent orchestration you should *mirror*, not import. |
| **Memory** | 10 memory types (short/working/long-term, project, business, prefs, decision/architecture histories, conversation, knowledge cache); namespace + classification ceilings; business writes approval-gated; most text search is substring | Typed `MESSAGE`/`DOCUMENT`/`FRAGMENT`/`DESCRIPTION`/`CUSTOM`; scopes `shared`/`private`/`room`/`global`/ACL partitions; async embedding queue; BM25 + advanced memory | **AIOS** for regulated enterprise memory policy; **elizaOS** for conversation/RAG memory ergonomics | Privacy + classification + approval are core to your vision. Borrow room/session scoping and async embed drain; keep Security Layer as PDP. |
| **RAG (document ingestion)** | Documentation Engine: PDF/DOCX/MD/YAML/JSON → Vector Search; ERP Knowledge Engine: schema sync, graph, formulas (approval-gated); default `HashingEmbedding` (lexical); optional Ollama embed (not live-tested); poll reindex, not watcher | `DocumentService` + `plugin-documents`: upload/bulk/URL/YouTube; chunk → embed → hybrid search (vector 0.6 + BM25 0.4); chat-augmentation injects fragments | **elizaOS** for general RAG product quality; AIOS stronger on **ERP schema/formula knowledge** | Your “continuous learning from docs + business rules” needs hybrid search + real semantic embeddings. Keep ERP Knowledge as AIOS differentiator; upgrade the vector path. |
| **Plugin system** | Phase 12: approve → install capability/template → Prompt Builder register → agents hot-reload; MCP register/activate separate; plugins ≈ new *agent capabilities* | Full `Plugin` interface: actions, providers, evaluators, services, models, routes, events, schema, views/widgets, dependencies, remote sandbox mode; ~147 plugins | **elizaOS** for extensibility surface; **AIOS** for “nothing loads without approval” | Your NFR maps cleanly to elizaOS’s actions/providers/models split — adopt that *shape* inside Capability Registry + extensibility, without Bun plugins. |
| **Model-agnostic support** | Ollama `/api/generate` only; per-capability `target_model` config override; Phase 23 Model Router designed as seed only | `useModel(ModelType)` + priority handlers; plugins: OpenAI, Anthropic, Ollama, Google GenAI, Groq, OpenRouter, xAI, Eliza Cloud, local GGUF | **elizaOS** clearly | Your vision explicitly requires vendor independence and cloud models behind approval. Phase 23 is the critical gap. |
| **Tool calling** | Structured tool bridges in Reasoning Engine (DB, shell, git, calc scripts, audit, …); allow-list + `POST /security/authorize` + audit; mutations propose → approve → resume | Two-stage loop: `HANDLE_RESPONSE` then native action tools; `ToolPolicyService` risk groups; results feed planner | **AIOS** for safety/governance of mutating tools; **elizaOS** for generic tool-loop ergonomics | Keep fail-closed governance. Borrow native tool-schema + iterative planner loop so tools are registry-driven, not hardcoded dispatch. |
| **REST API** | 11 FastAPI services; Gateway (`platform-spine`) for task entry; fail-closed if governance down; API surface indexed in Phase 21 | Unified `@elizaos/agent` HTTP+WS on ~2138; chat, memory, documents, plugins, models, orchestrator; OpenAI/Anthropic-compatible chat routes | **AIOS** for microservice replaceability; **elizaOS** for operator DX and streaming chat API | Your “API first + replaceable components” favors AIOS service boundaries. Borrow conversation/SSE/streaming patterns for Phase 24 BFF — not a single-port monolith. |
| **Web UI** | Phase 24 design only (`phase-24-control-ui.md`); no `web/` or `services/control-ui/` | Production Vite React shell + `@elizaos/ui`; widget slots; plugin views; desktop/mobile; Playwright e2e | **elizaOS** | Biggest product gap vs your “central intelligence” vision. Borrow layering (shell/ui/client/BFF) and approval-first chat — already planned in Phase 24. |
| **MCP support** | Approval-gated register/activate/invoke; **not** MCP JSON-RPC; only `POST {server}/invoke`; **not connected** to Reasoning Engine | Official MCP SDK; stdio + HTTP/SSE; tool/resource discovery; `MCP` action + provider; marketplace search | **elizaOS** | Your vision lists MCP servers as first-class tool adapters. AIOS must become a real MCP *client* behind governance, then expose tools to Planner/Reasoning Engine. |
| **Local deployment** | `docker-compose.yml` + 11 Dockerfiles (unverified here — no daemon); Ollama in topology; `deploy/backup.sh` / `restore.sh` live-drilled | `bun run dev` (API+UI); PGlite default; Docker deploy toolkit; optional bootable OS images | **elizaOS** for day-1 DX; **AIOS** for multi-service production topology + proven backup drill | Offline-first is aligned on both. AIOS needs a verified Compose path and a simpler “one command brings kernel up” developer experience. |

---

## Where AIOS already wins (do not regress)

These are deliberate advantages over elizaOS for *your* product:

1. **Governance-first PDP** — authorize → audit → approval expire-to-reject; fail closed if Security Layer unreachable.
2. **ERP Brain depth** — Odoo/accounting/manufacturing/cutlist/calculation agents + ERP Knowledge Engine (schema, formulas).
3. **Structural sandbox for code mutation** — propose branch → human approve → merge; external coding agents treated as untrusted tools (Phase 22).
4. **Microservice replaceability** — swap one service without rewriting a 9k-line runtime.
5. **Honesty culture** — READMEs and phase docs distinguish real vs stub (e.g. hashing embeddings, MCP invoke stub, Docker unverified).

---

## What to borrow from eliza-develop (upgrade roadmap)

Prioritized for your vision and the NFR *AIOS owns workflow; third parties are plugins*. Adopt **patterns** into Python services; never import `eliza-develop/`.

### P0 — blocks the vision

| Borrow | From elizaOS | Into AIOS | Why |
|---|---|---|---|
| **Typed Model Router** | `useModel(ModelType)` + provider plugins + priority fallback | **Phase 23** — register Ollama / OpenAI / Anthropic / Gemini / … behind roles (`TEXT_LARGE`, `CODE`, `EMBEDDING`); cloud calls classification-gated | Vendor independence is a primary objective and currently unmet |
| **Real MCP client** | `plugin-mcp` (SDK, stdio/HTTP/SSE, discovery) | Upgrade `services/extensibility` MCP Client; wire discovered tools into Reasoning Engine / Planner as governed actions | MCP servers are named first-class adapters in your vision |
| **Control UI** | app / ui / app-core layering, widget slots, swarm-style activity stream | **Phase 24** as already designed — chat → Gateway tasks, approval inbox, ops widgets | No operator surface = not yet a usable “operating system” |
| **Semantic + hybrid RAG** | DocumentService hybrid weights, async embed queue, chat augmentation | Replace default `HashingEmbedding` with real embed model; add BM25/hybrid; inject fragments in Context Builder | Continuous learning from docs needs real retrieval quality |

### P1 — strengthens “third parties are plugins”

| Borrow | From elizaOS | Into AIOS | Why |
|---|---|---|---|
| **Actions vs Providers split** | Actions = side effects; Providers = context | Capability Registry = actions; Context Builder adapters = providers; enforce in schema | Makes VS Code / OpenCode / Odoo / Git adapters uniform plugin surfaces |
| **Plugin dependency topo-sort + fail-closed resolve** | Plugin `dependencies`, DFS load, skip missing refs | Capability packages declare deps; Registry fails closed | Matches your replaceable-adapter rule |
| **Optional plugin views** | `views` + `/api/views/<id>/bundle.js` | Phase 12 + 24 `view_manifest` | Extensibility without hardcoding UI pages |
| **Conversation / room scoping** | World → Room → Entity | `conversation_id` on tasks (Phase 24) → Memory scopes | Multi-agent + multi-channel memory without ad-hoc sockets |

### P2 — polish orchestration (keep AIOS as owner)

| Borrow | From elizaOS | Into AIOS | Why |
|---|---|---|---|
| **Native tool-schema planner loop** | Stage-2 iterative tool calls with trajectory limits | Evolve Reasoning Engine tool dispatch from hardcoded bridges → registry-driven schemas (still authorize every call) | Tool-agnostic NFR |
| **SwarmActivity-shaped events** | Typed envelopes over WS | Phase 22/24 SSE timeline for coding sessions + multi-agent steps | Operator visibility |
| **ACP coding-agent orchestration patterns** | `plugin-agent-orchestrator` task/workspace lifecycle | Extend Phase 22 gateway once Docker sandbox is available | Live OpenCode/Claude Code as *plugins*, AIOS still merges |
| **Dev DX: bind API first, defer heavy boot** | app-core bind-first boot | Compose healthchecks + Gateway readiness before agents | Local deployment friction |

### Explicitly do **not** borrow

- Bun/TypeScript `AgentRuntime` as the kernel
- Discord/Telegram character connectors as core
- Chat that executes mutating tools without Security Layer + approval
- Eliza Cloud as a required dependency
- Replacing microservice boundaries with a single agent process

---

## Adapter map (NFR applied)

Your intended ownership model, mapped to where each project stands:

| Third party | Your intended role | AIOS today | elizaOS today | Gap to close in AIOS |
|---|---|---|---|---|
| VS Code | plugin | Not a first-class adapter | App / IDE adjacent | Define IDE adapter interface |
| OpenCode / Claude Code | plugin | Phase 22 gateway (safety-gated) | ACP orchestrator (live on desktop) | Safe sandbox + full session lifecycle |
| Ollama / Qwen / DeepSeek / Llama | model adapters | Ollama only, config override | Provider plugins + ModelType | Phase 23 |
| OpenAI / Anthropic / Gemini | model adapters (approval-gated) | Absent | Present | Phase 23 + classification rules |
| MCP servers | tool adapters | Simplified invoke stub | Real MCP client | Real protocol + RE wiring |
| GitHub/GitLab | repository adapters | Git Manager (local repo/sandbox) | Issues lifecycle in orchestrator | Remote SCM adapter behind governance |
| Odoo | ERP adapter | Odoo agent + DB connector + ERP knowledge | N/A (not ERP-focused) | Keep / deepen — AIOS advantage |
| Django | framework adapter | Django agent | N/A | Keep |

---

## Related docs

| Doc | Role |
|---|---|
| [`architecture-vision.md`](architecture-vision.md) | Two brains, Model Router gap |
| [`elizaos-borrowed-ideas.md`](elizaos-borrowed-ideas.md) | Patterns we already chose to adopt |
| [`eliza-develop-technical-reference.md`](eliza-develop-technical-reference.md) | External framework deep dive |
| [`requirements-alignment-assessment.md`](requirements-alignment-assessment.md) | Are we building to your requirements? |
| [`phase-24-control-ui.md`](phase-24-control-ui.md) | Planned operator UI |
| Root [`README.md`](../README.md) | Built vs designed status table |

---

*Comparison grounded in AIOS `services/` + honesty READMEs and the `eliza-develop/` checkout (elizaOS 2.0.x). Update this doc when Phase 23/24 land or MCP Client graduates from stub.*
