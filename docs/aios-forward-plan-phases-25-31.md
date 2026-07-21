# AIOS — Finalized Forward Plan
### Review of the Proposed Restructure · New Phases 25–31

*Companion to `docs/aios-architecture-and-phases.md` and `docs/requirements-alignment-assessment.md`. Written as a planning document — nothing here is built yet.*

---

## Part 1 — Review of the Proposed Structure

The proposed layout (aios_core / model_adapters / ide_adapters / agent_framework / tool_adapters / memory / knowledge / workflows / security / plugins) is a **good conceptual taxonomy and a costly physical migration**. The distinction matters: the value of that structure is the *idea* that models, IDEs, and tools are replaceable adapters behind stable contracts — not where files sit on disk. Your own `requirements-alignment-assessment.md` already asks for exactly this ("codify adapter interfaces for IDE/SCM/MCP so new integrations can't bypass them"), and that is an interface-contract problem, not a folder problem.

### Mapping: proposed folder → what actually exists

| Proposed | Reality in the repo today | Verdict |
|---|---|---|
| `aios_core/` | `services/platform-spine` + `assembly` + `planning` + `knowledge` — the kernel | Exists. Keep as services |
| `model_adapters/ollama,openai,anthropic,gemini` | `services/agents/.../model_router.py` — OllamaProvider, OpenAIProvider, AnthropicProvider, GeminiProvider classes already written | Exists as code. Document, don't move |
| `ide_adapters/vscode,cursor,continue,opencode` | Nothing — the genuine gap | **New — but NOT as per-IDE code** (see below) |
| `agent_framework/` (6 agents) | `services/agents/` — 23 agents, each `capability.yaml` + `template.md` + `register.py` | Exists, richer than proposed |
| `tool_adapters/git,terminal` | `services/execution/` (Phase 6, sandboxed) | Exists |
| `tool_adapters/mysql,postgresql` | `services/database/` (Phase 7, dry-run-gated) | Exists |
| `tool_adapters/browser,odoo,django,docker` | Partial or missing — odoo is knowledge-level not live; browser doesn't exist | **Genuine gaps → Phase 29** |
| `memory/`, `knowledge/` | `services/knowledge/` + `knowledge_pipelines/` | Exists |
| `workflows/` | Task manager + planner exist; no declarative multi-step workflow layer | **Genuine gap → Phase 30** |
| `security/` | `services/governance/` — the most complete part of the whole system | Exists |
| `plugins/` | `services/extensibility/` — shell exists, MCP client unwired | Exists as shell → wired in Phase 26 |
| *(not in proposal)* | `assembly` (context/prompt building), `observability`, `control-ui` + `web/`, audit hash chain, approval inbox | The proposal silently drops these — they must survive any reorganization |

### What to adopt from the proposal

1. **The adapter framing as enforced contracts** — a published `ModelProvider` / `ToolAdapter` / `IDESurface` interface set, with a rule that agents may not call third parties except through a registered adapter. This becomes Phase 28.
2. **`workflows/` as a first-class concept** — declarative multi-agent workflows are a real missing layer. Becomes Phase 30.
3. **The `future_models/` signal** — extensibility by declaration. Already how the model router is shaped; Phase 28 formalizes it.

### What to reject, and why

1. **The big-bang restructure.** Moving 12 tested services into a new tree rewrites every import, test path, deploy script, docker-compose entry, and doc link — weeks of churn, zero new capability, high breakage risk. If a physical move is ever wanted, do it opportunistically per-service when that service is being touched anyway, never as a project.
2. **Per-IDE adapter folders (`ide_adapters/vscode/`, `cursor/`, ...).** This implies bespoke integration code per editor — the exact complexity you said you don't want, and it ages badly (every new editor = new folder). The correct architecture is **one MCP server + one OpenAI-compatible endpoint = every IDE**, because VS Code (Continue), Cursor, OpenCode, and Claude Code all already speak those two protocols. Per-IDE material reduces to a config recipe of a few lines each, which belongs in `docs/ide-recipes/`, not in code.
3. **"aios_core is the only permanent part."** In this architecture the invariant is **governance** — authorize → audit → approve is what everything routes through and what nothing may bypass. Better mental model, concentric rings: governance + kernel (permanent) → agents (configuration) → adapters (replaceable) → external tools/models/IDEs (plugged in).

**Bottom line:** capture the taxonomy as a one-page architecture map in `docs/` (this document's table is the seed), adopt its two genuinely new ideas as Phases 28 and 30, and leave the working tree alone.

---

## Part 2 — New Phases

Sequencing logic, consistent with how Phases 1–24 were ordered: fix quality of what exists before adding surface area (25); build the two concrete IDE surfaces before abstracting their contract (26–27 before 28 — same "don't design interfaces against zero implementations" rule used in Phases 4–5); contracts before more adapters (28 before 29); orchestration UX once the surfaces exist (30); team hardening last, before anyone else touches it (31).

---

### Phase 25 — Model & Retrieval Quality (no new hardware)

**Why first:** the single biggest quality problem today is invisible: vector search still runs on the Phase 3 lexical hashing embedding, so "semantic" retrieval is really keyword overlap. Fixing it is one env var plus a small model that runs on current hardware. Nothing else in the plan pays off as much per hour of work.

**Scope**
- Pull `nomic-embed-text` (~270 MB) in Ollama; set `EMBEDDING_BACKEND=ollama`; re-ingest/reindex existing documents (the ingestion contract was built for exactly this swap in Phase 3 — no code change expected, verify only).
- Upgrade the reasoning model within current RAM: test `qwen2.5-coder:7b`; keep `qwen3.2:4b` as the router's fallback candidate.
- Verify the model router's `has_model()` pre-flight against the actual pulled tags (it already exists; confirm it passes with the new models).
- Measure before/after: a small fixed set of retrieval queries against ERP docs, and one coding task per agent tier, recorded in the phase doc so the improvement is evidence, not impression.

**Explicitly out:** any cloud provider activation; any new service.
**Effort:** Small (days). **Depends on:** nothing new.

---

### Phase 26 — MCP Surface (the IDE integration) + wire the MCP client

**Why now, why MCP-first:** with a 4B-class local model, AIOS-as-model-backend would make IDE coding *worse* than the IDE's own model. What AIOS uniquely has is domain knowledge, 23 governed agents, approvals, and audit. MCP exposes exactly that: the IDE's strong model does the typing, AIOS is the governed brain it consults. One server, every editor.

**Scope**
- New small service (`services/mcp-surface/`, port 8025) speaking MCP over HTTP/stdio, exposing ~8 tools:
  `submit_task`, `get_task_status`, `ask_agent(capability, question)`, `search_knowledge`, `get_erp_schema`, `list_pending_approvals`, `get_audit_trail(task_id)`, `list_capabilities`.
- Every tool call routes through the existing gateway/authorize path — the MCP surface is a thin translator, never a bypass. Same BFF discipline as control-ui (Phase 24).
- **Approval *decisions* deliberately excluded** from the MCP surface: an AI-driven IDE session must not be able to approve its own risky actions. Deciding stays in the web UI only.
- Wire the existing MCP *client* stub (extensibility service) into the Reasoning Engine as a real tool source, closing the "MCP not real/wired" gap in your own assessment — same protocol work, same phase.
- `docs/ide-recipes/`: one short connection recipe each for Claude Code (`claude mcp add aios ...`), Cursor, VS Code+Continue, OpenCode. Documentation, not code.

**Effort:** Medium (1–2 weeks). **Depends on:** nothing; Phase 25 recommended first only so the knowledge the IDEs query is worth querying.

---

### Phase 27 — OpenAI-Compatible Endpoint (the GPU-day switch)

**Why it exists:** the day the GPU server arrives, AIOS should be selectable as the *model provider* inside any IDE — confidential code then flows through AIOS's own classification and routing instead of a vendor's cloud. Building the shim now (it's small) means GPU day is a config flip, not a project.

**Scope**
- `/v1/chat/completions` (+ `/v1/models`) shim on the gateway, with streaming (SSE) — the minimum surface Continue/Cursor/OpenCode need to treat AIOS as a custom provider.
- Requests route through classification (Phase 4) + model router (Phase 23): confidential-classified content is structurally barred from any cloud provider candidate, provable in the audit log.
- Auth via the same gateway token mechanism (upgraded properly in Phase 31).

**Effort:** Small–Medium (days–1 week). **Depends on:** model router (exists). Buildable any time; *valuable* at GPU arrival.

---

### Phase 28 — Adapter Contracts (the good idea from the proposed structure, done as enforcement)

**Why after 26–27:** by now there are three real, working adapter families to generalize from — model providers (Phase 23), the MCP surface (26), the OpenAI surface (27). Contracts extracted from working implementations, not invented in a vacuum.

**Scope**
- Publish versioned interface contracts in `docs/contracts/`: `ModelProvider` (formalize what model_router already does), `ToolAdapter` (what execution/database already are), `IDESurface` (what 26/27 are).
- The structural rule from your assessment doc, made real: **agents may not make bespoke third-party calls** — Security Layer denies outbound calls from agent code that don't go through a registered adapter. Policy + a lint/CI check, not convention.
- Adapter registry entry added to the capability registry so Planner and the ops UI can see what adapters exist, mirroring how agents are already visible.

**Effort:** Medium. Mostly judgment and enforcement wiring, little new runtime code. **Depends on:** 26, 27.

---

### Phase 29 — Tool Adapter Gaps (browser, live Odoo, live Django)

**Why these three:** they're the rows in the proposed `tool_adapters/` list that are genuinely missing rather than renamed. Built *under* the Phase 28 contracts — first proof the contract regime works for new adapters.

**Scope**
- **Odoo live adapter:** XML-RPC/JSON-RPC against a real Odoo 19 instance — read-only first (records, workflows states), upgrading Odoo Agent's `odoo.read_orm` from cached-schema to live-scoped reads; writes stay propose-then-approve exactly as Phase 5 designed.
- **Django management adapter:** governed `manage.py` invocation through the existing Shell Executor allow-list (check, showmigrations, test) — no new execution engine, new allow-list entries + adapter wrapper.
- **Browser adapter:** headless Playwright behind Shell Executor's sandbox, read/screenshot-first, gated like every other mutating tool for any interaction beyond reading. Feeds Research Agent and Testing Agent.

**Effort:** Medium–Large (each adapter is small; three of them plus a real Odoo test instance is the bulk). **Depends on:** 28.

---

### Phase 30 — Declarative Workflows

**Why:** the second genuinely new idea from the proposed structure, and it matches your assessment doc's "polished multi-agent runtime UX / auto-run delegated tasks" gap. Today a multi-agent flow exists only as Planner's dynamic decomposition; there's no way to *save* a proven flow ("on MR open: code_review_agent → testing_agent → summarize to approvals") and re-run it.

**Scope**
- Workflow definition format (YAML) referencing existing capabilities + depends_on — deliberately reusing the Phase 8 task-graph schema rather than inventing a second graph model.
- Workflow store + trigger endpoints (manual, and via the MCP surface so an IDE can invoke a saved workflow by name).
- Runs appear in the existing web UI timeline; every step still individually approval-gated per its capability — a workflow batches orchestration, never batches consent.

**Effort:** Medium. **Depends on:** 26 (trigger surface), 8 (task graph, exists).

---

### Phase 31 — Team & GPU-Day Hardening

**Why last:** everything above works single-operator on current hardware. This phase is the gate between "my dev machine" and "team on a shared Ubuntu server + GPU," which you named as the eventual target.

**Scope**
- Replace the Phase 2 token-stub auth with real auth (self-hosted OIDC/LDAP per the offline-first mandate) across gateway, control-ui, MCP surface, and the OpenAI endpoint — the single actual blocker for multi-user.
- Per-user identity flowing into the existing audit chain and approval routing (approver ≠ requester enforcement becomes meaningful with real users).
- GPU-day playbook, written and rehearsed: pull the large model on the server → point `OLLAMA_URL` at it → flip default model in config → Phase 27 endpoint becomes primary for IDE model traffic → embeddings unchanged. A config change with a checklist, because Phases 25–27 made it one.
- Existing Phase 19 docker-compose is the deployment vehicle; this phase only fills its named auth/secrets honesty-gaps.

**Effort:** Medium. **Depends on:** all above only in the sense that it hardens them.

---

## Summary Table

| Phase | Delivers | Effort | Unblocks |
|---|---|---|---|
| 25 | Real semantic retrieval + better local coder model | S | Everything downstream being worth querying |
| 26 | MCP surface → all four IDEs + MCP client wired | M | IDE integration, 30's triggers |
| 27 | OpenAI-compatible endpoint | S–M | GPU-day switch |
| 28 | Enforced adapter contracts | M | 29, structural NFR |
| 29 | Browser / live-Odoo / Django adapters | M–L | Real ERP depth |
| 30 | Saved declarative workflows | M | Multi-agent UX |
| 31 | Real auth + GPU playbook | M | Team rollout |

**Not in this plan, deliberately:** a physical repo restructure (rejected above, revisit only opportunistically); building an AIOS-native IDE UI (the web UI stays an operator console — approvals, audit, ops — which is the one thing the IDEs can't do); activating cloud model keys before classification gating is proven under Phase 27 (privacy-first stays the default, cloud stays opt-in per the original mandate).
