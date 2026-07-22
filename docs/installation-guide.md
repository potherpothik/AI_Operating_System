# AI Operating System — Installation Guide

This guide gets you from a fresh machine to a **working local stack** with:

- Ollama + **qwen3.2:4b** (your current model)
- Backend microservices
- Web Control UI (chat, approvals, ops)

Quick command reference: [`command.txt`](command.txt).

Architecture reference: [`aios-architecture-and-phases.md`](aios-architecture-and-phases.md).

---

## 1. What you are installing

| Component | Role | Default port |
|---|---|---|
| **governance** | Security, audit, approvals | 8000 |
| **platform-spine** | Gateway + tasks + config | 8002 |
| **knowledge** | Memory + vector search | 8003 |
| **assembly** | Context + prompt builder | 8004 |
| **agents** | Reasoning Engine + 23 agents | 8005 |
| **execution** | Shell + git sandbox | 8006 |
| **database** | DB connector | 8007 |
| **planning** | Planner + capability registry | 8008 |
| **knowledge_pipelines** | Docs + ERP knowledge + code analysis | 8009 |
| **extensibility** | Plugins + MCP client | 8010 |
| **observability** | Health + metrics | **8013** (for Web UI) |
| **control-ui** | BFF for browser | 8024 |
| **web** | React operator UI | 3000 |
| **Ollama** | Local LLM | 11434 |

All Python services default to **SQLite** (zero DB setup). Postgres + pgvector is the production path.

---

## 2. Prerequisites

### Required

| Tool | Version | Check |
|---|---|---|
| **Linux** (or WSL2) | — | Your environment |
| **Python** | 3.11+ | `python3 --version` |
| **pip** | recent | `pip --version` |
| **Node.js** | 18+ | `node --version` |
| **npm** | 9+ | `npm --version` |
| **Git** | any recent | `git --version` |
| **Ollama** | installed | `ollama --version` |

### Optional (production / full features)

| Tool | Purpose |
|---|---|
| **PostgreSQL 16 + pgvector** | Real vector search, multi-service DB |
| **Docker + Compose** | Phase 19 deployment topology |
| **Demo ERP Postgres** | Phase 7/9 database agent + ERP knowledge (`DEMO_ERP_DATABASE_URL`) |

---

## 3. Install Ollama and your model

You already have Ollama running with **qwen3.2:4b**. Verify:

```bash
ollama list
curl -s http://localhost:11434/api/tags | python3 -m json.tool
```

If Ollama is not running:

```bash
ollama serve
```

Pull the model (skip if already present):

```bash
ollama pull qwen3.2:4b
```

**Important:** shipped config defaults to `qwen-coder`, which you may not have pulled. After starting **platform-spine**, override config to your model (see [Section 6](#6-point-the-system-at-qwen324b)).

---

## 4. Clone and prepare the repo

```bash
cd /home/saadi/Documents/AI_Operating_System   # or your clone path
```

Create sandbox directories (git proposals, plugins):

```bash
mkdir -p /tmp/ai_os_sandbox /tmp/ai_os_plugins
```

Optional — clone a repo the agents can propose changes against:

```bash
git clone https://github.com/you/your-project.git /tmp/ai_os_sandbox/your-real-repo-clone
```

---

## 5. Install Python dependencies

```bash
cd /home/saadi/Documents/AI_Operating_System
python3.12 -m venv .venv    # use python3.12 — full deps including psycopg2-binary
source .venv/bin/activate
pip install --upgrade pip
```

Install per service (includes `psycopg2-binary` on Python 3.12):

```bash
for svc in governance platform-spine knowledge assembly agents execution \
           database planning knowledge_pipelines extensibility observability control-ui; do
  pip install -r "services/$svc/requirements.txt"
done
```

If only `python3` (3.14) is available and `psycopg2-binary` fails to build, either install Python 3.12 or skip that line for SQLite-only dev:

```bash
grep -v '^psycopg2-binary' services/governance/requirements.txt | pip install -r /dev/stdin
```

### Install Web UI

```bash
cd web
npm install
cd ..
```

### Quick start script (recommended)

After venv + deps are installed:

```bash
./deploy/run-local.sh start   # all backend services (logs in deploy/logs/)
cd web && npm run dev         # http://localhost:3000
./deploy/run-local.sh stop    # when finished
```

Set your Ollama model tag if needed:

```bash
AIOS_LOCAL_MODEL=qwen3.2:4b ./deploy/run-local.sh start
```

---

## 6. Point the system at qwen3.2:4b

Default `reasoning_engine.yaml` names `qwen-coder` / `deepseek-coder`. The Model Router (Phase 23) checks Ollama for **actually pulled** models.

After **governance** and **platform-spine** are running:

```bash
curl -X POST http://localhost:8002/config/override \
  -H "Authorization: Bearer dev-admin-token" \
  -H "Content-Type: application/json" \
  -d '{"service":"reasoning_engine","key":"default_local_model","value":"qwen3.2:4b","set_by":"human_admin"}'

curl -X POST http://localhost:8002/config/override \
  -H "Authorization: Bearer dev-admin-token" \
  -H "Content-Type: application/json" \
  -d '{"service":"reasoning_engine","key":"fallback_local_model","value":"qwen3.2:4b","set_by":"human_admin"}'
```

Verify:

```bash
curl -s http://localhost:8002/config/reasoning_engine \
  -H "Authorization: Bearer dev-admin-token"
```

You can also pass `"target_model":"qwen3.2:4b"` on direct `/reasoning/execute` calls.

---

## 7. Start services

**Rule:** start **governance (8000) first**. Gateway fails closed if it is down.

**Rule:** start **Ollama** before **agents (8005)**.

Copy-paste commands for every terminal are in [`command.txt`](command.txt).

### Minimal stack (Web UI + chat)

| # | Service | Port |
|---|---|---|
| 1 | governance | 8000 |
| 2 | platform-spine | 8002 |
| 3 | knowledge | 8003 |
| 4 | assembly | 8004 |
| 5 | agents | 8005 |
| 6 | control-ui | 8024 |
| 7 | web (`npm run dev`) | 3000 |

Optional: **observability on 8013** for the Ops page (Web UI proxies `/health` and `/metrics` to 8013).

### Full stack

Add execution, database, planning, knowledge_pipelines, extensibility, observability — see [`command.txt`](command.txt).

After planning is up:

```bash
curl -X POST http://localhost:8008/capabilities/sync \
  -H "Authorization: Bearer dev-admin-token"
```

---

## 8. Open the Web UI

1. Browse to **http://localhost:3000**
2. Sign in with token **`dev-admin-token`** (pre-filled in dev)
3. **Chat** — creates real tasks via Gateway (not direct tool execution)
4. **Approvals** — approve/reject pending mutations
5. **Ops** — health/metrics (needs observability on :8013)

---

## 9. Verify installation

```bash
# Governance alive
curl -s http://localhost:8000/security/policy/human_admin | head -c 200

# BFF bootstrap (needs control-ui + governance + platform-spine)
curl -s -H "Authorization: Bearer dev-admin-token" http://localhost:8024/ui/bootstrap

# Create a task
curl -s -X POST http://localhost:8002/api/v1/tasks \
  -H "Authorization: Bearer dev-admin-token" \
  -H "Content-Type: application/json" \
  -d '{"title":"Install smoke test","description":"Say hello and confirm agents work","requested_by":"human_admin","priority":"normal"}'

# System health (observability)
curl -s http://localhost:8013/health/system
```

Run service tests:

```bash
cd services/governance && pytest tests/ -q
cd services/control-ui && PHASE1_PATH=../governance PHASE2_PATH=../platform-spine pytest tests/ -q
```

---

## 10. Optional: PostgreSQL

For production-like vector search (pgvector):

1. Install Postgres 16 + pgvector extension
2. Set `DATABASE_URL` per service README before starting each service
3. Use `docker compose` (Phase 19) for an all-in-one topology:

```bash
cp .env.example .env
# Edit: POSTGRES_PASSWORD, DEMO_ERP_DATABASE_URL, GATEWAY_TOKEN
docker compose build
docker compose up -d
```

**Honesty:** Compose covers all backend services as of Phase 31, including **control-ui**, **web**, **mcp-surface**, and **identity** (a real, pre-existing gap for the first three — found and fixed during Phase 31's own docker-compose review, since they were built after this file was first written and nothing came back to add them). Compose was written to the real interface but may be unverified on your machine until you run `docker compose up`.

Backup/restore scripts: `deploy/backup.sh`, `deploy/restore.sh` — see [`aios-architecture-and-phases.md#phase-20-backup-strategy-disaster-recovery`](aios-architecture-and-phases.md#phase-20-backup-strategy-disaster-recovery).

---

## 11. Optional: ERP database (Phase 7 / 9)

To use Database Agent and ERP Knowledge Engine against a real DB:

1. Set `DEMO_ERP_DATABASE_URL` where **governance** runs (see `governance/security/secrets_registry.yaml`)
2. Start **database** (:8007) and **knowledge_pipelines** (:8009)
3. Sync schema:

```bash
curl -X POST http://localhost:8009/erp-knowledge/sync \
  -H "Authorization: Bearer dev-admin-token" \
  -H "Content-Type: application/json" \
  -d '{"target_db":"demo_erp"}'
```

Without this, DB migrate endpoints report `not_configured` — expected in a docs-only dev setup.

---

## 12. Ingest your project knowledge

With **knowledge_pipelines** running:

```bash
curl -X POST http://localhost:8009/docs/ingest \
  -H "Authorization: Bearer dev-admin-token" \
  -H "Content-Type: application/json" \
  -d '{"path":"/absolute/path/to/your/doc.pdf","project_id":"my_project","doc_type":"architecture"}'
```

Query vectors:

```bash
curl -X POST http://localhost:8003/vector/query \
  -H "Content-Type: application/json" \
  -d '{"project_id":"my_project","query":"Odoo manufacturing","top_k":5,"classification_ceiling":"internal"}'
```

**Note:** default embeddings are lexical (hashing) unless you configure Ollama embeddings — see `services/knowledge/README.md`.

---

## 13. Known limitations (read before production)

| Topic | Dev reality |
|---|---|
| **Auth** | Default is still the Phase 2 stub token file (`AUTH_MODE=stub`); a real self-hosted OIDC option exists (`AUTH_MODE=oidc`, Phase 31 — `services/identity/`) but isn't the default, and MCP Surface's own per-request wiring is honestly deferred |
| **Sandbox** | Subprocess fallback without Docker — not full isolation |
| **Cloud LLMs** | Model Router interfaces exist; providers return `not_configured` unless you add API keys + governance approval |
| **MCP** | Simplified HTTP invoke stub — not full MCP protocol in agent loop |
| **External coding agents** | Phase 22 gateway refuses unsafe live sessions without Docker sandbox |
| **UI** | Capability views and Settings page not built yet; no workflow-runs view (Phase 30) |

Service-level honesty: each `services/<name>/README.md`.

---

## 14. Troubleshooting

| Problem | Fix |
|---|---|
| Gateway returns “security layer unreachable” | Start governance on :8000 first |
| Agent errors / empty model response | Check `ollama list`; set config override to `qwen3.2:4b` |
| Chat creates task but no answer | Ensure agents :8005 + assembly :8004 + knowledge :8003 are up |
| Ops page fetch errors | Start observability on **8013** (or change `OBSERVABILITY_URL` + `web/vite.config.ts`) |
| `AllCandidatesExhausted` for model | Override `default_local_model` / `fallback_local_model` to a pulled tag |
| 401 on API calls | Header: `Authorization: Bearer dev-admin-token` |
| Planner finds no capabilities | `POST /capabilities/sync` on :8008 |

---

## 15. Next steps

1. Use Chat daily for ERP/coding questions  
2. Ingest architecture and Odoo/Django docs  
3. Practice approval workflow on propose-only actions  
4. Read [`aios-architecture-and-phases.md`](aios-architecture-and-phases.md) for phase details  
5. Add agents via `.cursor/skills/add-agent-capability/SKILL.md` when you need new domains  

---

## Related docs

| Doc | Purpose |
|---|---|
| [`command.txt`](command.txt) | Copy-paste terminal commands |
| [`README.md`](README.md) | Doc index + service → phase map |
| Root [`README.md`](../README.md) | Status table + honesty notes |
| [`architecture-vision.md`](architecture-vision.md) | Long-term vision |
