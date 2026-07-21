# Adapter Contracts (Phase 28)

Versioned interface contracts extracted from three real, working
implementations — not invented in advance of any of them. Phase 26 (MCP
Surface) and Phase 27 (OpenAI-Compatible Endpoint) were built before this
doc, on purpose: "don't design interfaces against zero implementations,"
the same rule Phases 4→5 already followed for Context Builder before the
first agent existed.

| Contract | Formalizes | Real implementations today |
|---|---|---|
| [`model-provider.md`](model-provider.md) | How AIOS calls a model | `OllamaProvider`, `OpenAIProvider`, `AnthropicProvider`, `GeminiProvider` (`services/agents/agents/reasoning_engine/model_router.py`, Phase 23) |
| [`tool-adapter.md`](tool-adapter.md) | How AIOS calls a tool | Shell Executor, Git Manager (`services/execution/`, Phase 6), Database Connector (`services/database/`, Phase 7), MCP Client (`services/extensibility/`, Phase 12) |
| [`ide-surface.md`](ide-surface.md) | How an external IDE calls AIOS | MCP Surface (`services/mcp-surface/`, Phase 26), OpenAI-Compatible Shim (`services/platform-spine/platform_spine/gateway/openai_shim.py`, Phase 27) |

## The structural rule this phase enforces

**Agent code may not make bespoke third-party calls.** Every network call
an agent capability or Reasoning Engine bridge makes must go through a
registered adapter — `agents/clients.py` (internal AIOS service calls),
`model_router.py`/`ollama_adapter.py` (model calls), or an MCP-registered
external server (Phase 12's approval-gated registration). This was
already this codebase's own convention since Phase 5 (every bridge calls
`clients.something()`, never raw `httpx` directly) — Phase 28 makes it
enforced, not just followed by habit: `services/agents/tests/test_adapter_boundary.py`
statically scans every module under `services/agents/agents/` and fails
if any file outside the allowlisted adapter modules imports `httpx` or
`requests` directly. Real, run by the normal test suite, not a
convention documented and hoped for.

## What's still just documentation, not runtime enforcement

Nothing here adds a Security-Layer-side network interceptor that blocks
an outbound call at the OS/process level — that would require sandboxing
every agent-code call site the way Shell Executor already sandboxes
shell commands (Phase 6), which is a materially larger project than this
phase's own "mostly judgment and enforcement wiring, little new runtime
code" scope. The real enforcement here is static (the lint check above),
not dynamic. A future phase could add process-level network egress
control if agent code ever runs less-trusted, model-generated logic
directly rather than through these fixed, human-written bridge modules.
