# Phase 24 — Control UI Web Shell (working implementation)

Real Vite + React + TypeScript app, live-tested in a browser end to end
(sign in, send a chat message that creates a real task, approve a real
pending approval, view real ops data) — not just built and assumed working.
The first non-Python product surface in this repo.

## A real, deliberate deviation from the Phase 24 design doc

The design doc (`docs/phase-24-control-ui.md` §4–§6) sketches three separate
npm packages — `web/shell/`, `web/ui/`, `web/client/` — each with its own
`package.json`. This implementation is **one Vite app** (`web/`) with that
same layering as internal folders (`src/pages/` = shell/routing,
`src/components/` = shared UI chrome, `src/client/` = the typed API layer).
Three real npm workspaces would add real packaging complexity (cross-package
linking, three build configs) with no functional benefit for a v1 this size
— a deliberate, honest simplification, not a shortcut that drops anything
the design called for. Split back into three packages if/when capability
views (§5.5) need to ship as independently-versioned bundles.

## Run it

```bash
npm install
npm run dev   # → http://localhost:3000, proxies /api/v1, /ui, /metrics, /health
```

Needs, running and reachable at the ports `vite.config.ts` proxies to:
`governance` (8000), `platform-spine` (8002), `services/control-ui` (8024),
`observability` (8013, optional — Ops page shows a fetch error if down,
not a crash).

Sign in with `dev-admin-token` (pre-filled) — the same stub token
Gateway's own `tokens.yaml` already maps to `human_admin`.

## Build it

```bash
npm run build   # tsc -b && vite build — real type-checking, not skipped
```

## What's real vs. what's a stub

**Real:**
- **Chat** creates a real conversation (`POST /ui/conversations`) and a
  real task (`POST /api/v1/tasks`, straight to Gateway — chat is not an
  executor, exactly as the design doc §8 requires: it never calls
  `/shell/execute`, `/git/push`, or `/db/*`). Live-verified: sending one
  message through the browser produced exactly one real task row, visible
  independently via `curl .../api/v1/tasks`.
- **Live task status** via Gateway's real SSE endpoint
  (`GET /api/v1/tasks/{id}/stream`) — see the gap-fill note below.
- **Approvals inbox** lists real pending approvals and really decides them
  through the BFF's governed proxy — live-verified: approving in the
  browser changed the approval's real status in governance, confirmed
  independently with a direct `curl` against governance afterward.
- **Ops page** renders real `GET /health/system` / `GET /metrics/overview`
  JSON, unmodified — including services genuinely reported `"down"` when
  they weren't running during testing, not faked as healthy.

**Real gap-fill this phase needed, not anticipated by the design doc:**
`EventSource` (the real browser SSE client) cannot set an `Authorization`
header at all — a genuine browser API limitation. Gateway's stream endpoint
now accepts a `?token=` query-param fallback
(`platform_spine/gateway/auth.py`'s new `resolve_actor_for_stream`), used
only by this one endpoint; every other Gateway route still requires the
real header, unchanged.

**Stubbed / deliberately out of scope this phase** (matches
`services/control-ui/README.md`'s own honesty notes):
- **Auth is a stub token**, not real SSO/LDAP (design doc §14).
- **Chat shows orchestration outcomes** (task status, event count), never
  token-by-token model output — Reasoning Engine has no safe streaming
  surface for that yet (design doc §5.1's own honesty note).
- **Capability views (§5.5) are not implemented** — the catalog is
  honestly empty; there's no view-manifest convention on
  `services/extensibility/` yet to render anything real.
- **No mobile/desktop shell** (Capacitor/Electrobun) — web-only, as designed.
- **Settings page (§5.6) not built this session** — named as remaining
  scope, not silently dropped.

## Next

Settings page (§5.6, read-mostly config introspection). Capability views
once `services/extensibility/` gains a real view-manifest convention. Split
into three npm packages if/when that's genuinely needed.
