# ElizaOS Borrowed Ideas

### Study notes — ideas borrowed, framework not adopted

This document records architectural ideas taken from studying the ElizaOS
monorepo (local checkout under `eliza-develop/`, gitignored, not a runtime
dependency). The AI Operating System remains a Python FastAPI microservices
orchestration layer. Nothing here imports ElizaOS code.

Primary study locus: `eliza-develop/packages/core` (`AgentRuntime`, types,
message loop); plugins under `eliza-develop/plugins/`.

---

## 1. Plugin architecture

**What ElizaOS does:** a `Plugin` interface registers actions, providers,
evaluators, services, model handlers, events, and routes. Plugins declare
`dependencies`; the host topo-sorts them (DFS, cycle-detect). Discovery
(catalog / `plugins.json`) is separate from runtime registration. Missing
resolvers fail closed — string refs are skipped, not invented.

**Borrow into this repo:**
- Treat capabilities as declarative packages with explicit `dependencies`
  and topo-load order.
- Keep catalog discovery (Capability Registry) separate from runtime
  registration (Reasoning Engine + executors).
- Fail closed if a named capability cannot resolve.
- Map ElizaOS `autoEnable` (env / connector gated) → env-gated activation
  in the Capability Registry.
- Extend [`services/extensibility/`](../services/extensibility/) (Phase 12
  MCP Client / Plugin System) rather than inventing a parallel plugin
  mechanism.

---

## 2. Agent communication

**What ElizaOS does:** World → Room → Entity scoping. Multi-agent talk is
usually "shared room + message memories," or orchestration plugins that
spawn child agents and inject completion memories back into the parent.
Connectors normalize inbound into `Memory` + room/world, then call the
message service.

**Borrow into this repo:**
- Use World / Room / Entity (or equivalent session / conversation /
  participant IDs) as future multi-agent and multi-channel scoping for
  Memory and Task Manager.
- Prefer "post into shared room" or "spawn child run + inject completion"
  over ad-hoc agent-to-agent sockets.
- Keep channel adapters thin: normalize → orchestrator.
- Today agent handoff already uses Task Manager + Planner + `delegate_to`
  (see Agent Communication Protocol in
  [`aios-architecture-and-phases.md#ai-orchestration-layer-remaining-roadmap`](aios-architecture-and-phases.md#ai-orchestration-layer-remaining-roadmap));
  room scoping is the natural next refinement, not a rewrite.

---

## 3. Memory design

**What ElizaOS does:** typed memories (`document | fragment | message |
description | custom`) with scopes (`shared | private | room | …`).
Embeddings are async (batch queue) so they never block the turn. Providers
compose "recent messages + ranked facts + optional vector docs" rather than
one mega-query. Facts use BM25 + confidence × recency decay by design.

**Borrow into this repo:**
- Split store types (messages vs facts vs document fragments) under
  [`services/knowledge/`](../services/knowledge/).
- Scope every row by room / agent / world (or today's correlation /
  session equivalents) as those IDs land.
- Compose "recent window + ranked facts + vector docs" inside Context
  Builder source adapters ([`services/assembly/`](../services/assembly/)).
- Keep embedding generation on an async queue so retrieval richness never
  blocks reply latency (aligns with Phase 3's existing vector path).

---

## 4. Tool registry (actions vs providers)

**What ElizaOS does:** **Actions** = side-effect tools with `validate` then
`handler`, results summarized back into the planner loop. **Providers** =
context suppliers (`get()` → `{text, values, data}`), not executors.
Evaluators run post-turn (facts, relationships).

**Borrow into this repo:**
- Capability Registry + governed executors = actions (`validate` +
  `execute` + structured result fed back to Planner).
- Context Builder source adapters = providers (context gates / always-on
  flags).
- Keep "read context" and "do side effects" as separate registration
  surfaces — maps cleanly to assembly vs `services/execution/` /
  `services/database/`.
- Every action still goes through Security Layer authorize + audit
  (governance-first; ElizaOS does not replace that contract).

---

## 5. Runtime (`composeState` / `useModel`)

**What ElizaOS does:** `AgentRuntime` owns character settings, plugin list,
action/provider/evaluator registries, a `models` map of handlers, services,
events, and DB adapter. `composeState` selects providers and merges into
prompt state. `useModel(modelType, params)` picks the highest-priority
handler for a typed model role (`TEXT_LARGE`, `TEXT_EMBEDDING`, …).

**Borrow into this repo:**
- One turn orchestrator (Reasoning Engine + Planner) owns capability +
  model registries and a compose step before reasoning — already close to
  today's assembly → agents flow.
- Ollama (and future backends) register behind abstract model *types* with
  priority — this is the seed for **Phase 23 Model Router**, not a Phase
  22 deliverable.
- Long-lived adapters as services resolved by type string (same pattern as
  executor / connector microservices behind a registry).

---

## 6. Message bus / event system

**What ElizaOS does:** a typed internal `EventType` bus
(`MESSAGE_RECEIVED`, `ACTION_*`, `MODEL_*`, `EMBEDDING_GENERATION_*`, …)
plus a thin UI notifier. The critical path is a synchronous stage pipeline
(message → hooks → composeState → planner → evaluators); async queues are
only for embeddings / background work.

**Borrow into this repo:**
- Eventually publish a small typed event enum across FastAPI services
  (`message_received`, `action_started`, `embedding_requested`,
  `error_reported`) with fail-visible handlers.
- Keep the critical path as a clear stage pipeline; use async queues only
  for embeddings / background work.
- Governance can sit on `action_started` / authorize-before-handler the
  same way private actions and tool policy are gated today.
- **Deliberately not built yet.** Current agent communication is
  Task-Manager-mediated (Phase 8 / phases 12–21). A bus is an alternative
  evolution, not a required rewrite of what works.

---

## 7. Web UI / control plane

**What ElizaOS does:** a four-layer frontend — `packages/app` (Vite shell),
`packages/ui` (React components), `packages/app-core` (boot + API client),
`packages/agent/api` (HTTP + WebSocket on default port 2138). Plugins declare
`views` with `bundlePath`; the server serves `/api/views/<id>/bundle.js`.
Widget slots (`chat-sidebar`, `home`, `nav-page`, …) let plugins contribute
dashboard tiles without hardcoding pages in the shell. Dev mode proxies `/api`
and `/ws` from Vite to the agent. Swarm inline chat renders
`SwarmActivityEnvelope` events (message, tool, plan, lifecycle) over WebSocket
for multi-agent step trees. Mobile/desktop use Capacitor/Electrobun with null
stubs for desktop-only plugins.

**Borrow into this repo:**
- Mirror the **layering**: `web/shell` + `web/ui` + `web/client` + existing
  FastAPI microservices, with a thin **`services/control-ui/` BFF** for
  aggregation and governed write proxy — not a second orchestrator.
- **Dev proxy**: Vite → Gateway (`/api/v1`) + BFF (`/ui`) + observability
  peers; single operator port in local dev.
- **Widget slots** for Phase 13 ops (metrics, health), approval inbox, and
  task status — implements the frontend Phase 13 explicitly deferred.
- **Capability-declared views**: extend Phase 12 extensibility with optional
  `view_manifest` + bundle hosting at `/ui/views/{id}/bundle.js` (catalog
  discovery separate from runtime registration, same rule as plugins).
- **Conversation scoping** instead of World/Room/Entity in v1:
  `conversation_id` on Gateway tasks groups chat turns; optional later link to
  Memory Manager `MESSAGE` rows (sections 2–3).
- **Streaming**: reuse Gateway `GET /api/v1/tasks/{id}/stream` (SSE) for live
  task status; Phase 22 adds coding-session step events to the same timeline
  (SwarmActivity-shaped, validated at BFF boundary).
- **Governance-first chat**: the composer submits **`POST /api/v1/tasks`**, not
  direct `/reasoning/execute`. Approvals are a first-class inbox surface
  (`approval.decide` always authorize-gated). This is the critical divergence
  from elizaOS AgentRuntime chat.

**Agents implementing Phase 24 must read this section** before writing Control UI code.

Full design: [`aios-architecture-and-phases.md#phase-24-control-ui-web-shell`](aios-architecture-and-phases.md#phase-24-control-ui-web-shell).

---

## Cross-cutting mapping

| ElizaOS | AI Operating System |
|---|---|
| Plugin + dependencies | Capability packages + Capability Registry; extend `services/extensibility/` |
| Providers | Context Builder source adapters (`services/assembly/`) |
| Actions + validate/handler | Planner tools → shell/git/DB executors via governance |
| `composeState` | Context Builder composition API |
| `useModel` / ModelType | Future Model Router (Phase 23) over Ollama |
| Memory scopes + FACTS/RECENT | Memory + vector service (`services/knowledge/`) |
| World/Room/Entity | `conversation_id` on tasks (Phase 24); later Memory scopes |
| `EventType` + messageService | Optional internal bus + turn orchestrator (not built) |
| Web shell / ui / app-core | `web/shell`, `web/ui`, `web/client`, `services/control-ui/` |
| Plugin `views` + bundles | Extensibility view manifests + `/ui/views/*` hosting |
| Widget slots | Control UI widget registry (chat-sidebar, ops-home, …) |
| SwarmActivity inline trace | Phase 22 coding-session events on task SSE / BFF stream |

---

## Explicitly not borrowed

- ElizaOS TypeScript/Bun runtime, character files, Discord/Telegram
  connectors, or any package as a dependency.
- Adopting ElizaOS's plugin loader or plugin marketplace.
- Replacing governance with ElizaOS tool policy — Security Layer remains
  the PDP.
- `@elizaos/app`, `@elizaos/ui`, monolithic agent server on one port, or
  chat that executes actions without Security Layer + approval.
- Capacitor / Electrobun / mobile null-stub pattern (web-only v1).

---

## Next

When implementing **Phase 24 (Control UI)**, re-read section 7 and
[`aios-architecture-and-phases.md#phase-24-control-ui-web-shell`](aios-architecture-and-phases.md#phase-24-control-ui-web-shell). When implementing Phase 22
(external coding agents) or Phase 23 (Model Router), re-read sections 4–5.
When adding multi-agent session scoping to Memory, re-read sections 2–3. Do
not pull `eliza-develop/` into the runtime path.
