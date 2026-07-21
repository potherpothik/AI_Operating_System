# `IDESurface` contract — v1

Formalizes the shape both real IDE-facing surfaces already share —
`services/mcp-surface/` (Phase 26) and
`services/platform-spine/platform_spine/gateway/openai_shim.py`
(Phase 27). Two protocols, one shape, extracted after both were real and
working — "one MCP server + one OpenAI-compatible endpoint = every IDE"
(the forward plan's own framing for why per-IDE adapter folders were
rejected).

## The shape

1. **A fixed, stub-auth actor identity per surface**, not per human user.
   `mcp_surface` (Phase 26) and `ide_client` (Phase 27) are both real
   governance roles with real bearer tokens (`tokens.yaml`), but every
   session through a given surface shares the same identity — the audit
   trail records "an MCP session did X," not "person Y did X." Real per-
   user auth is explicitly deferred to Phase 31 for both surfaces, named
   as a known gap rather than silently assumed away.
2. **Every call authorizes and audit-logs through the real Security
   Layer before touching anything** — a thin translator, never a bypass.
   MCP Surface's `_gate()` helper and the OpenAI shim's
   `authorize()`/`audit_log()` calls are the same two-step pattern,
   independently implemented, converging on the same shape.
3. **Structurally excluded from approval-deciding.** MCP Surface has no
   `decide_approval`-shaped tool anywhere, and no governance role grant
   that would make one meaningful. The OpenAI shim has no tool-calling
   surface at all — an IDE using it for chat completions can't reach
   approval-gated actions through this surface in the first place. An
   AI-driven session must never be able to approve its own risky action;
   both surfaces satisfy this by construction, not by convention.
4. **Reuses existing governed mechanisms, adds no second copy of them.**
   MCP Surface's `submit_task`/`ask_agent` call the same real Gateway/
   Reasoning Engine paths a human using Control UI would. The OpenAI
   shim's model access calls the same real `model_router`/
   `ollama_adapter` code every agent's own reasoning loop already uses
   — Phase 27 added new HTTP endpoints
   (`/reasoning/raw_generate*`) to reach that existing code, not a
   second model-calling implementation.
5. **Content-sensitivity gating happens BEFORE the underlying call, not
   after.** The OpenAI shim's classification-vs-ceiling check
   (`services/governance/`'s classify + `services/assembly/`'s
   `ceiling_for_model()`) refuses before any model call. MCP Surface
   doesn't need an equivalent for its own tools since none of its 8
   tools release content to an external model at all — the distinction
   is real, not an oversight: this surface exposes AIOS's OWN governed
   agents/knowledge, never a third-party model.

## Real implementations (v1)

| Surface | Protocol | Real per-user auth |
|---|---|---|
| MCP Surface | Real MCP JSON-RPC 2.0 (streamable HTTP) | No — fixed `mcp_surface` actor (Phase 31) |
| OpenAI-Compatible Shim | OpenAI chat-completions REST + SSE | No — fixed `ide_client` actor (Phase 31) |

## Versioning

v1 = the shape as it exists after Phase 27. A genuinely new IDE-facing
protocol (unlikely — the whole point of this contract is that MCP and
OpenAI-compatible already cover every real IDE) would be the first real
test of whether this shape generalizes further.
