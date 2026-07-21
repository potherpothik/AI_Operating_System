# Requirements Alignment Assessment — AI Operating System

### Is AIOS being built according to your stated requirements?

**Short answer:** Directionally **yes** on privacy, governance, modularity, ERP+coding brains, and “propose don’t auto-mutate.” Materially **no / incomplete** on model-agnostic routing, real MCP as tool adapters, operator Web UI, polished multi-agent runtime UX, and structural enforcement that *every* third party is only a replaceable plugin.

Companion comparison with elizaOS: [`aios-vs-eliza-develop-comparison.md`](aios-vs-eliza-develop-comparison.md).

---

## How this assessment works

Each requirement is scored:

| Score | Meaning |
|---|---|
| **Aligned** | Built and matches the intent (honesty notes allowed) |
| **Partial** | Designed and/or partially built; gaps block the claim |
| **Gap** | Required by vision but missing or contradicted by current architecture |
| **Risk** | Present direction could drift away from the NFR if not corrected |

Your non-functional requirement used as a lens on every row:

> **AIOS owns the workflow; third-party tools are plugins.**

---

## Vision & design principles

| Requirement | Score | Evidence | Modification needed |
|---|---|---|---|
| Privacy first / offline first | **Aligned** | Local Ollama default; secrets via governance; no cloud required for core path | Keep cloud models *optional* and classification-gated when Phase 23 adds them |
| Vendor / framework / model independence | **Partial** | Microservice architecture is vendor-independent; **runtime models are Ollama-only** | Implement **Phase 23 Model Router** with provider adapters (OpenAI, Anthropic, Gemini, Ollama, …) |
| Modular / replaceable components | **Aligned** | 11 independently runnable services; agents as capability config | Codify adapter interfaces for IDE/SCM/MCP so new integrations can’t bypass them |
| Tool / model / framework agnostic | **Partial** | Capability allow-lists + Git/DB/shell bridges; models not agnostic yet | Registry-driven tools + Model Router; stop growing hardcoded tool dispatch in Reasoning Engine |
| Security by default / human controlled | **Aligned** | Authorize → audit → approve; approvals expire to reject; fail closed | Preserve as non-negotiable when borrowing elizaOS UX patterns |
| Documentation driven / API first | **Aligned** | Design docs before code; FastAPI per service; Phase 21 API index | Continue; update built-phase docs when gap-filling |
| Self-improving | **Partial** | Code analysis, research/docs agents, knowledge pipelines | Close the loop with real semantic RAG + operator feedback UI |
| Extensible for future technologies | **Partial** | Plugin System + MCP Client shell exist | Plugins must cover models, tools, IDEs, MCP — not only new agent YAML |
| **AIOS owns workflow; third parties are plugins** | **Partial / Risk** | Kernel owns Planner/Task/RE/governance; plugins/MCP exist but MCP is stub and not wired; no hard rule preventing bespoke HTTP integrations | See [Structural NFR enforcement](#structural-nfr-enforcement) below |

---

## Primary objectives

| Objective | Score | Current state | Modification needed |
|---|---|---|---|
| Vendor-independent platform | **Partial** | Independent of Eliza/LangChain; dependent on Ollama for generation | Multi-provider Model Router (Phase 23) |
| Coordinate coding agents, local LLMs, MCP, tools, IDEs | **Partial** | Coding gateway designed/gated; Ollama yes; MCP not real/wired; no VS Code adapter | Real MCP client → RE; IDE adapter interface; finish Phase 22 sandbox path |
| Full SDLC assistance | **Partial** | Agents for plan, code review, test, docs, devops, reverse eng, architecture | Control UI + stronger multi-agent execution (auto-run delegated tasks) |
| Engineering brain for Odoo / Django / calculations | **Aligned** | ERP + coding brains; Phases 5, 7, 9–11, 14–18, 22 | Keep deepening ERP adapters; don’t dilute into general chatbot product |
| Protect proprietary code on local infra | **Aligned** | Sandbox, propose/approve, classification | Maintain when adding cloud models |
| Continuous learning from docs, APIs, repos | **Partial** | Doc ingest + vector store + ERP knowledge; weak embeddings; poll reindex | Semantic embeddings, hybrid search, Context Builder augmentation |
| Modular replaceable external components | **Partial** | Philosophy yes; enforcement incomplete | Adapter registry + deny direct third-party calls from agents |
| Standardized interfaces (tools, models, memory, agents) | **Partial** | Memory types, capability.yaml, message format (Phase 21); models/tools uneven | Publish stable adapter contracts; align with actions/providers split |
| Autonomous execution with approval for sensitive ops | **Aligned** | Working pattern across DB/git/formulas/coding proposals | Ensure UI makes approval inbox first-class (Phase 24) |
| Reusable beyond ERP | **Partial** | Kernel is reusable; product still ERP-heavy (by design) | Keep domain agents as plugins/capabilities on shared kernel |

---

## Core capabilities checklist

| Capability | Score | Notes |
|---|---|---|
| Control VS Code, OpenCode, Git, Docker, terminals, browsers | **Partial** | Git + shell + Docker *agent* + coding gateway exist; VS Code/browser not first-class plugins |
| Select best model per task from multiple providers | **Gap** | Config override to Ollama model name only — no router |
| Manage specialized collaborating agents | **Partial** | Many specialists; `delegate_to` does not auto-schedule; no parallel Planner executor |
| Build/maintain project knowledge | **Partial** | Real pipelines; retrieval quality limited by hashing embeddings |
| Generate / analyze / refactor / test / review / document code | **Aligned** | Agent fleet + execution sandbox + code analysis |
| Reverse engineering / system analysis | **Aligned** | Phase 16 agents |
| MCP servers + extensible tool adapters | **Gap** | MCP Client is HTTP invoke stub; not JSON-RPC; not in agent loop |
| Monitor progress / memory across sessions | **Partial** | Task Manager + memory types; no Control UI; weak conversation scoping |
| Continuously improve own architecture safely | **Partial** | Docs + analysis agents; no self-modification without same governance (good) |

---

## Gap analysis → required modifications

Ordered by impact on your stated vision.

### 1. Phase 23 — Model Router (P0)

**Problem:** Vision says model-agnostic; code is Ollama-only.

**Do:**
- Design full phase doc (seed exists in [`architecture-vision.md`](architecture-vision.md) §3).
- Introduce typed roles (`TEXT_LARGE`, `CODE`, `EMBEDDING`, …) with priority-ordered handlers.
- Adapters: Ollama first; OpenAI / Anthropic / Gemini as approval-gated plugins.
- Never read raw long-lived keys in agents — resolve via governance/secrets pattern.

**Borrow:** elizaOS `useModel(ModelType)` idea only ([`elizaos-borrowed-ideas.md`](elizaos-borrowed-ideas.md) §5).

### 2. Real MCP Client + Reasoning Engine wiring (P0)

**Problem:** Extensibility “MCP” is not MCP; agents cannot use MCP tools.

**Do:**
- Implement MCP JSON-RPC client (stdio + HTTP/SSE) in `services/extensibility`.
- Discover tools/resources; map each to a governed action (`mcp.invoke` + per-tool allow-list).
- Reasoning Engine / Planner must select MCP tools like any other capability — results labeled untrusted until validated.
- Keep fail-closed if server unreachable.

**Borrow:** elizaOS `plugin-mcp` transport/discovery patterns, not its TypeScript package.

### 3. Phase 24 — Control UI (P0)

**Problem:** No operator surface; an “OS” without a console.

**Do:** Build as designed in [`aios-architecture-and-phases.md#phase-24-control-ui-web-shell`](aios-architecture-and-phases.md#phase-24-control-ui-web-shell):
- Chat → `POST /api/v1/tasks` (not raw `/reasoning/execute`).
- Approval inbox, ops widgets (Phase 13), capability views.
- SSE task/coding-session timeline.

**Borrow:** UI layering + widget slots from elizaOS; keep governance-first chat.

### 4. RAG quality upgrade (P0/P1)

**Problem:** Default hashing embeddings undermine “continuous learning.”

**Do:**
- Make a real embedding model the default (Ollama embed or dedicated model via Model Router).
- Add hybrid (vector + BM25) retrieval in Vector Search.
- Context Builder: always compose recent + ranked facts + doc fragments (elizaOS provider composition).
- Optional: background reindex watcher (today is poll-only).

### 5. Enforce “third parties are plugins” structurally (P1)

**Problem:** NFR is cultural, not an invariant. New code can still hardcode HTTP to OpenCode/Odoo/etc.

**Do:**
- Define a single **Adapter Registry** (extend Capability Registry / extensibility):
  - `model_adapter`, `tool_adapter` (incl. MCP), `repo_adapter`, `ide_adapter`, `erp_adapter`, `framework_adapter`
- Policy: Reasoning Engine may only call adapters listed in the registry.
- CI / lint rule or architecture test: ban direct SDK imports of third-party agent CLIs from `services/agents` except through `coding_agent_gateway`.
- Plugin packages declare `dependencies` + required permissions; fail closed on missing resolvers (elizaOS pattern).

### 6. Multi-agent execution hardening (P1)

**Problem:** Planner graphs and `delegate_to` don’t fully run collaboration.

**Do:**
- Auto-enqueue delegated tasks to Task Manager with explicit status (not overloaded `needs_clarification`).
- Optional parallel executor for independent Planner subtasks (still per-action authorize).
- Conversation/room scoping on Memory + tasks for shared agent context.

### 7. Finish external coding agent path (P1)

**Problem:** Phase 22 correctly refuses unsafe sessions; live OpenCode/Claude Code not usable yet.

**Do:**
- Require Docker (or stronger) sandbox backend for live ACP sessions.
- Treat OpenCode/Claude Code strictly as plugins behind Coding Agent Gateway.
- Same propose → approve → merge gate as local model output (already designed — complete when sandbox exists).

### 8. Local deployment DX (P2)

**Problem:** Compose exists but unverified; multi-terminal bootstrap is heavy.

**Do:**
- Verify `docker-compose` on a machine with Docker; add healthchecks.
- One-shot `make up` / script that brings governance → spine → knowledge → agents.
- Document offline profile (no cloud keys) as the default.

### 9. IDE / SCM / browser adapters (P2)

**Problem:** Vision lists VS Code, browsers, GitHub/GitLab; only local Git/shell are strong.

**Do:**
- Spec `ide_adapter` (VS Code extension or MCP-based bridge).
- Spec `repo_adapter` for GitHub/GitLab (PR/issue) behind governance.
- Browser automation only via sandbox allow-list + approval for mutating flows.

---

## Structural NFR enforcement

Today:

```
AIOS kernel owns: Gateway → Task Manager → Planner → Reasoning Engine → Governance → Executors
Third parties:    partial plugins (capabilities), stub MCP, gated coding gateway
Bypass risk:      future direct HTTP/SDK calls from agent code
```

Target:

```
User / UI / IDE plugin
        ↓
   Gateway (only task entry)
        ↓
 Planner + Reasoning Engine  ←── Model Router (adapters)
        ↓
 Adapter Registry only:
   tool | mcp | git | erp | ide | coding-cli | db
        ↓
 Governance authorize + audit (+ approval if needed)
        ↓
 Concrete backend (Ollama, OpenCode, Odoo, MCP server, …)
```

**Success criterion:** Replacing OpenCode, Ollama, or an MCP server requires changing **one adapter package** and registry config — zero changes to Planner, Security Layer, or Task Manager.

---

## What is already on track (do not rethink)

Keep building on these — they already match the requirements:

1. Design-doc-first phases with honesty notes  
2. Governance as mandatory PDP for mutating work  
3. Two brains (`brain: erp | coding`) on one kernel  
4. Agents as config (`capability.yaml` + template), not new FastAPI apps  
5. External coding agents as untrusted tools (Phase 22 philosophy)  
6. ERP Knowledge + Documentation pipelines as first-class knowledge paths  
7. Refusing to adopt elizaOS as the runtime (study only)

---

## Suggested build order (next 4 milestones)

| Milestone | Outcome |
|---|---|
| **M1** | Phase 23 Model Router (Ollama + one cloud provider behind approval) |
| **M2** | Real MCP Client + wire into Reasoning Engine as governed tools |
| **M3** | RAG: real embeddings + hybrid search + Context Builder composition |
| **M4** | Phase 24 Control UI (chat, approvals, ops) |

Then: multi-agent auto-delegate, Docker-verified coding gateway, IDE/SCM adapters, Adapter Registry enforcement tests.

---

## Verdict

| Question | Answer |
|---|---|
| Is the project going according to your requirements? | **Mostly in architecture and governance; not yet in product completeness.** |
| Biggest mismatches | Model lock-in (Ollama), MCP stub, no Web UI, weak semantic RAG, incomplete “everything is a plugin” enforcement |
| Biggest strengths vs requirements | Privacy/governance, ERP+coding specialization, replaceable microservices, honest stubs, human approval for mutations |
| Should you rewrite on elizaOS? | **No.** Borrow patterns (model router, MCP, UI layering, actions/providers). Keep AIOS as the workflow owner. |

---

## Related docs

- [`aios-vs-eliza-develop-comparison.md`](aios-vs-eliza-develop-comparison.md)
- [`architecture-vision.md`](architecture-vision.md)
- [`elizaos-borrowed-ideas.md`](elizaos-borrowed-ideas.md)
- Root [`README.md`](../README.md) status table

---

*Assessment date: 2026-07-21. Re-score after Phase 23, real MCP, and Phase 24 land.*
