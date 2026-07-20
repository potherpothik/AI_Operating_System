# Phase 19 — Deployment Architecture · Docker Deployment

---

## Prerequisites (read before implementation)

| Doc | Why |
|---|---|
| [`docs/README.md`](README.md) | Doc index and before-you-code checklist |
| [`phases-12-21-remaining-subsystems.md`](phases-12-21-remaining-subsystems.md) Phase 19 | The master roadmap's own illustrative compose skeleton — this doc adapts it to the real, as-built module boundaries |
| Root [`README.md`](../README.md) | The authoritative real service → port → env-var map every file in this phase is built from |

---

## 0. Priority Decision: Why This Phase Now

**Why it exists here:** every service through Phase 18 has been run and tested as a bare `uvicorn` process against a real Postgres instance on one host — real, but not yet packaged as something a second machine could actually stand up. This phase closes that gap: real Dockerfiles, a real `docker-compose.yml`, and a real multi-database Postgres init script, all built from the actual, current 11-service topology rather than the master roadmap's own illustrative skeleton.

**Why adapt the master doc's skeleton rather than use it verbatim:** the Phase 19 design block in `phases-12-21-remaining-subsystems.md` was written speculatively, before most of this system existed, at a finer module granularity than what actually got built — it lists `security-layer`, `audit-logger`, and `approval-layer` as three separate containers, but the real Phase 1 build consolidated all three into one `services/governance/` FastAPI app; it lists `context-builder`/`prompt-builder` as two containers where the real build is one `services/assembly/`; `shell-executor`/`git-manager` as two where the real build is one `services/execution/`. The doc's own topology *principles* (one container per deployable unit, network segmentation by trust tier, secrets never baked into images) are sound and are what this phase actually implements — just applied to the real eleven deployable units, not the fifteen-plus illustrative ones. Building Dockerfiles for containers that don't correspond to anything real would be actively misleading.

**Alternatives considered**
- *Kubernetes* — rejected, matching the master doc's own reasoning: the stated stack names Docker + Docker Compose explicitly, not K8s, and single-host Compose keeps operational complexity proportional to what reads as one company's internal deployment. Noted as a future extension if multi-host scale is ever needed.
- *One shared container for multiple services* — rejected. "Modular, replaceable" is a stated top-level priority (`docs/architecture-vision.md`); one container per service keeps that real at the deployment layer, not just in the source tree.
- *A separate Postgres instance per service* — rejected for this phase. The real dev/test convention already established since Phase 7 is one Postgres instance, multiple logical databases (confirmed live throughout Phases 15–18's own test setup) — `docker-compose.yml` keeps that same shape with a real multi-database init script, not eleven separate stateful containers to operate.
- *Building and testing these containers against a live Docker daemon in this environment* — not available. No `docker` binary exists here (confirmed directly, the same constraint `DockerSandbox` has carried since Phase 6). Every artifact in this phase is written to the real Docker/Compose interface and is internally consistent with what's actually built, but is genuinely unbuilt and unverified against a live daemon in this environment — named honestly, the same posture `DockerSandbox` and `OllamaEmbedding` have carried since Phases 3 and 6.

**Trade-offs:** without a Docker daemon to build against, the real verification available this phase is structural — every `Dockerfile` matches its service's actual `requirements.txt`/`main.py`/real port; every `docker-compose.yml` env var matches exactly what that service's own README already documents reading; the compose file's own YAML parses and its service graph's `depends_on` chain matches the real, already-established call graph. That is real, meaningful verification, but it is not the same as a real `docker compose up` succeeding.

**Security implications:** the four-network topology (`public`/`internal`/`data-net`/`model-net`) mirrors Phase 6's "no network by default" sandboxing principle at the deployment layer — Gateway is the only service exposed on `public`; Shell Executor's own sandboxed subprocess network posture (Phase 6) is a separate, narrower concern this phase doesn't change. Secrets are declared via Docker's own `secrets:` mechanism (file-based, meant for a host-side SOPS+age or Vault-managed file), never as plain `environment:` values — consistent with `secrets_registry.yaml`'s own env-var-indirection posture (Phase 7) carried through to the deployment layer.

**Performance implications:** none evaluated — no live deployment to measure.

**Future scalability:** Kubernetes manifests are a natural follow-on once multi-host scale or existing K8s operations expertise makes it worthwhile; the one-container-per-service boundary this phase establishes is what a K8s migration would build directly on top of.

**Estimated complexity:** Medium. Eleven real, small Dockerfiles (a repeatable pattern once the first is right) plus one real compose file — genuinely new artifact types for this codebase, but no new application logic.

---

## 1. Real service → container map

| Container | Source | Port | Depends on |
|---|---|---|---|
| `governance` | `services/governance/` | 8000 | postgres |
| `platform-spine` | `services/platform-spine/` | 8002 | governance, postgres |
| `knowledge` | `services/knowledge/` | 8003 | governance, postgres |
| `assembly` | `services/assembly/` | 8004 | governance, platform-spine, knowledge |
| `execution` | `services/execution/` | 8006 | governance |
| `database` | `services/database/` | 8007 | governance, postgres |
| `planning` | `services/planning/` | 8008 | governance, agents, platform-spine, postgres |
| `knowledge_pipelines` | `services/knowledge_pipelines/` | 8009 | governance, knowledge, database, assembly, platform-spine, postgres |
| `extensibility` | `services/extensibility/` | 8010 | governance, assembly, agents, postgres |
| `agents` | `services/agents/` | 8005 | governance, platform-spine, knowledge, assembly, execution, database, knowledge_pipelines, ollama, postgres |
| `observability` | `services/observability/` | 8011 | every other service (read-only GETs), postgres |
| `postgres` | `pgvector/pgvector:pg16` | 5432 | — |
| `ollama` | `ollama/ollama:latest` | 11434 | — |

This is the real dependency graph established live across Phases 1–18's own test setup, not a re-derivation — `platform-spine`/`knowledge` depend only on `governance`; `assembly` depends on all three; `agents` depends on everything plus a local Ollama instance and calls back into `execution`/`database`/`knowledge_pipelines` for approved actions; `observability` depends on every other service but only ever issues read-only `GET`s, never a write, matching Phase 13's own "no write path to anything" design.

---

## 2. Networks

Four Docker networks, matching the master roadmap's own topology decision, applied to the real service list:

- **`public`** — `platform-spine` (Gateway) only. The single externally-reachable service.
- **`internal`** — every application service. Where all real service-to-service calls happen.
- **`data-net`** — `postgres`, reachable only by services that hold a real `DATABASE_URL`/target-database connection (all eleven application services, plus `database` specifically for `demo_erp`-shaped ERP targets).
- **`model-net`** — `ollama`, reachable only by `agents` (Reasoning Engine).

---

## 3. Dockerfiles

One per service (`services/<name>/Dockerfile`), same repeatable pattern:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser
EXPOSE <real port>
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "<real port>"]
```

Non-root user, matching Shell Executor's own `DockerSandbox` design (`--user 1000:1000`, Phase 6) — the same "don't run as root inside a container" posture this codebase already committed to for sandboxed execution, now applied to every long-running service container too. `python:3.12-slim`, matching the version this project's own `.venv` and every service's tests already run under (confirmed via `python3.12` throughout live testing since Phase 15).

`.dockerignore` (repo root) excludes `.venv/`, `__pycache__/`, `*.db` (SQLite dev artifacts), `eliza-develop/` (explicitly never a runtime dependency, Phase 13's own note carried forward), and each service's own `tests/`.

---

## 4. `docker-compose.yml`

Wires the real map in Section 1 together — real `environment:` blocks matching exactly what each service's own README already documents reading (cross-checked directly against every `## Run it` section, not re-derived), real `depends_on` chains, the four networks from Section 2, and Docker `secrets:` for `DEMO_ERP_DATABASE_URL`'s credential material rather than a plain environment value (mirroring `secrets_registry.yaml`'s own env-var-indirection stance, Phase 7). `ollama`'s GPU reservation block is present but commented out by default — offline-first must not assume a GPU exists, matching the master doc's own explicit note.

## 5. Postgres init

A real init script (`deploy/postgres-init/01-create-databases.sql`), run automatically by the official Postgres image's own `/docker-entrypoint-initdb.d/` convention — creates one logical database per service (`governance`, `platform`, `knowledge`, `assembly`, `agents`, `execution`, `database_connector`, `planning`, `knowledge_pipelines`, `extensibility`, `observability`), matching the exact naming convention already used live throughout Phases 15–18's own test setup on this same single Postgres instance. `pgvector/pgvector:pg16` (not a bare `postgres` image) — Vector Search (Phase 3) needs the `pgvector` extension available, the same image tag the master doc's own skeleton already specifies.

---

## 5.1 A real, named limitation: `depends_on` alone doesn't wait for readiness

None of these services declare a Compose `healthcheck:` — `depends_on` only orders container *start*, not "the other service's HTTP server is actually accepting requests yet" (every service here starts fast enough in practice during local testing that this hasn't mattered, but Compose gives no such guarantee). A real fix is a `healthcheck:` block per service (each one already has a real `GET /` or `GET /healthz` to hit) plus `condition: service_healthy` on every `depends_on` entry — a genuine, contained follow-up, not implemented this phase to keep the compose file's real scope matched to what's actually been cross-checked (Section 0's own honesty note).

## 6. Explicitly Out of Scope

Building or running any of this against a live Docker daemon — none exists in this environment (Section 0). Kubernetes manifests. Multi-host / multi-region topology. Automated CI image builds and registry publishing — a real, separate concern for whichever CI system a deployment target actually uses. TLS termination at Gateway (`ports: ["8443:8443"]` in the master doc's own illustrative skeleton implies it, but no certificate management is designed here) — a real gap, named rather than silently assumed solved.

---

## Next

Phase 20: Backup Strategy · Disaster Recovery — a real restore-drill design against the same Postgres data tier this phase's compose file stands up, plus the audit hash-chain verification (`GET /audit/verify`, Phase 1) already built as exactly the check a restore drill should run.
