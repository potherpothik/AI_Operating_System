---
name: add-new-service
description: >-
  Scaffolds a new Phase/subsystem FastAPI service in this AI Operating System
  repo, following the established design-doc-first, governance-wired,
  real-Postgres-tested pattern used by every existing service under services/.
  Use when the user asks to add a new service, subsystem, or phase that needs
  its own main.py. For a new agent capability only (capability.yaml +
  template.md), use the add-agent-capability skill instead.
---

# Add a New Service

## Workflow

Copy this checklist and work through it in order:

```
- [ ] 1. Write the design doc in docs/
- [ ] 2. Scaffold services/<name>/
- [ ] 3. Wire governance
- [ ] 4. Write tests
- [ ] 5. Write the service README with Honesty notes
- [ ] 6. Update the root README status table
```

### 1. Write the design doc in `docs/`

Create `docs/phase-N-<name>.md` (next unused phase number) before writing any
implementation code. Follow the skeleton used by every existing phase doc in
`docs/`:

- Title + module subtitle
- Priority Decision: why this subsystem now, alternatives considered, trade-offs, security implications, performance, future scalability, estimated complexity
- Per-module sections: Responsibilities, Inputs, Outputs, APIs, Failure handling, Logging, Security, Future extension points
- How the modules interact (ASCII flow)
- Minimal data model
- Folder structure
- Explicitly out of scope
- Next

### 2. Scaffold `services/<name>/`

```
services/<name>/
├── main.py              # FastAPI app, include_router(...)
├── requirements.txt
├── README.md
├── <package>/           # api.py, store.py, models, etc.
└── tests/
    ├── conftest.py
    └── test_*.py
```

Naming: directory lowercase with `-`/`_`; routes prefixed `/<domain>/...`;
actions named `domain.verb`. If this is an agent capability rather than a
standalone service, do not create a new FastAPI service at all — stop and
follow the `add-agent-capability` skill instead
(`.cursor/skills/add-agent-capability/SKILL.md`). That workflow adds
`capability.yaml` + `template.md` under `services/agents/agents/<name>/`
with `brain: erp | coding`, registers with the Capability Registry, and
syncs Planner.

### 3. Wire governance

- Point the new service at `SECURITY_LAYER_URL` (default `http://localhost:8000`) and call `POST /security/authorize` before any mutating action, then `POST /audit/log`.
- Add any new policy rules the service needs under governance's `policies/*.yaml`, then call `POST /security/reload`.
- If the service needs a database credential, register it in `secrets_registry.yaml` (`target_db` -> `{connection_string_env, allowed_capabilities}`) and resolve it via `POST /security/secrets/resolve` — never hardcode a connection string.
- Any mutating endpoint needs a dry-run/preview path plus a human-approval path (`POST /approval/request`) before it can execute for real.

### 4. Write tests

- `pytest tests/ -v`, matching the existing services' structure (`conftest.py` fixtures + `test_*.py`).
- Test against real Postgres wherever the feature touches a database — SQLite-only coverage is not equivalent. If Postgres isn't available in the environment, say so explicitly rather than presenting SQLite results as full coverage.
- If you hit a real bug during manual verification (not just unit tests), add a regression test that pins the fix instead of only patching it.

### 5. Write the service README

Include: what the service does, how to run it (`pip install -r requirements.txt`, `uvicorn main:app --port <N>`), how to test it, required env vars, and an explicit **Honesty notes** section listing anything stubbed, simplified, or not verified against a real dependency in this environment, plus how to swap it for the real thing. Model this on any existing `services/*/README.md`.

### 6. Update the root README status table

Add a row to the table in [`README.md`](../../../README.md) with the phase number, subsystem name, link to the design doc, link to the service directory, and test count. If anything in the new service is genuinely a stub, add a bullet to the root README's "Honesty notes worth reading before relying on this" section too.
