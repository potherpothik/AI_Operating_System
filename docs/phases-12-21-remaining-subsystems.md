# AI Orchestration Layer — Remaining Roadmap
### Phases 12–21

This completes the phase-by-phase design started in Phase 1. Phases 12–13 are genuinely new infrastructure and get full treatment. Phases 14–18 cover all sixteen remaining agents; since the agent pattern (`capability.yaml` + `template.md`, running on the shared Reasoning Engine, gated by Security Layer + Human Approval Layer, routed by Planner) is proven three times over by Phase 10, it's stated once below rather than re-derived per agent — each agent gets its capability declaration plus what's actually distinctive about it. Phases 19–21 close out the operational and consolidated-reference deliverables from the original 20.

**Open item carried forward:** the mandate lists "ERP Agent" and "Odoo Agent" separately. This roadmap continues treating Odoo Agent (Phase 5) as covering that ground, since Odoo is the ERP in this stack. Flag it if a distinct, broader cross-ERP agent is actually wanted.

---
---

# Part A — Extensibility & Observability Infrastructure

## Phase 12 — MCP Client · Plugin System

**Why this pairing, why now:** both are "let the system grow beyond what's built in" — MCP Client extends via external services, Plugin System via installable code. Same underlying question (how does this grow without punching a hole through Phase 1's governance), so designing them together keeps their approval and sandboxing story consistent instead of letting it drift apart. Deferred until now because nothing built through Phase 11 actually needed third-party extension yet — building this earlier would have been speculative.

**Alternative considered:** building extensibility earlier, e.g. right after Phase 1, so agents could lean on it from the start — rejected. Every module built since would then have had to design against a hypothetical plugin/MCP surface instead of concrete requirements; better to let real needs (the eighteen agents built so far) inform what extensibility actually has to support.

### MCP Client

**Responsibilities:** lets the orchestration layer consume external MCP servers as additional tools without a bespoke connector per integration. Every MCP tool call routes through the same `Security Layer.authorize()` and Human Approval Layer gating as any other tool call — MCP Client is a new tool *source*, not a new trust boundary. Servers are individually allow-listed and classified; registering one is approval-gated, mirroring capability registration (Phase 8). Defaults to local-only or explicitly-approved servers, consistent with offline-first — no automatic reach to arbitrary public MCP servers. Translates MCP tool schemas into the same action-pattern format Reasoning Engine and Security Layer already understand.

**APIs:** `POST /mcp/register` (approval-gated) · `POST /mcp/invoke` (Security-Layer-authorized) · `GET /mcp/servers`

**Failure handling:** unreachable server fails closed, tool marked unavailable, never silently skipped. A result outside the server's declared schema is rejected — the same "don't trust tool output blindly" discipline Reasoning Engine applies to model responses.

**Security:** an MCP server is effectively third-party code extending the tool surface, so it gets the most cautious default posture available: local-only by default, explicit approval for any remote server, and data returned from an MCP tool is tagged untrusted/retrieved content, same taint-tracking Vector Search results already carry.

**Future extension points:** a curated internal MCP catalog once a few servers are vetted; per-server rate limiting.

### Plugin System

**Responsibilities:** the mechanism for adding new agents or tool adapters without modifying core code — a plugin registers a `capability.yaml` + `template.md`, or a new tool adapter following Shell Executor/Database Connector's existing adapter pattern, through a defined interface. Discovery and loading validated against a manifest schema (name, version, declared capabilities, required permissions). A plugin's declared permissions go through the same approval gate as any capability registration — installed doesn't mean trusted by default. Executable plugin code reuses Shell Executor's sandbox rather than a separate plugin-specific one.

**APIs:** `POST /plugins/install` (approval-gated) · `POST /plugins/{id}/disable` · `GET /plugins`

**Failure handling:** a manifest claiming permissions it can't be verified to need is rejected at install time, not silently granted. A plugin causing runtime errors past a threshold is auto-disabled, not left running degraded.

**Security:** plugins are the most direct arbitrary-third-party-code surface in the system — same distrust as an MCP server, same gating, never granted broader classification ceiling or capability than explicitly approved at install.

**Future extension points:** a plugin marketplace mirroring Capability Registry's own noted future extension; versioned updates requiring re-approval on any permission change.

---

## Phase 13 — Metrics Dashboard · Health Monitor

**Why this pairing, why now:** both are read-only aggregation over data every prior phase already produces — no new instrumentation needed, just a place to look at it. Deferred until now because there was nothing meaningful to monitor before Phase 5's first agent existed, and little worth dashboarding before Phase 10's agent roster gave the system real usage variety.

### Health Monitor

**Responsibilities:** liveness/readiness checks across every module built since Phase 2's Gateway `/healthz`, aggregated into one system view. Surfaces degraded states already *defined* in earlier phases but with nowhere to report to until now: Security Layer unreachable (a system-halt condition per Phase 1), stuck tasks (Task Manager's SLA flag, Phase 2), stale ERP knowledge (Phase 9's `stale` flag), reasoning executions stuck past `max_iterations` (Phase 5). Deliberately does not auto-remediate — surfaces problems for a human, consistent with the system's human-in-the-loop philosophy throughout; auto-restarting a stuck module without review could mask a real problem.

**APIs:** `GET /health/system` · `GET /health/{module}` · `POST /health/alert-config` (reuses Human Approval Layer's offline-capable notification hook, Phase 1)

### Metrics Dashboard

**Responsibilities:** aggregates operational metrics already generated as a byproduct of every phase's own logging — task throughput/latency (Task Manager), reasoning iterations per task (Reasoning Engine), approval queue depth and time-to-decision (Human Approval Layer), tool execution volume by capability (Shell Executor/Database Connector), classification distribution of served content (Vector Search/Context Builder). Read-only by design — a dashboard that could mutate system state would need the full governance treatment everything else gets, so it deliberately doesn't get write access to anything.

**APIs:** `GET /metrics/overview` · `GET /metrics/{category}` · `GET /metrics/export`

**Security (both modules):** read-only means failures here never risk system state — worst case is a stale or unavailable view, never a bad write. Access is still classification-scoped: a viewer without clearance for confidential-tier activity sees aggregate counts, not task content at that tier. Access itself is logged lightly, since even aggregated metrics can be sensitive (an approval-queue count hints at pending risky actions).

**Future extension points:** real-time streaming (websocket) instead of polling; anomaly detection on metrics feeding back into Security Layer as a signal — e.g. an unusual spike in approval requests from one capability.

---
---

# Part B — Remaining Agents

**Shared baseline for every agent below** (established Phases 4/5/7/8, not repeated per agent): runs on the shared Reasoning Engine via `capability.yaml` + `template.md`; structured output — `reasoning, answer_or_proposal, confidence, provenance[], risk_classification, delegate_to?`; mutating actions require dry-run/preview plus Human Approval Layer, executed through Git Manager or Database Connector, never direct; registered in Capability Registry so Planner routes to it with zero new Planner code; logged identically — Reasoning Engine trace plus agent-level outcome plus the relevant execution-layer log.

## Phase 14 — Financial & Inventory Agents

**Why batched together:** all three touch the ERP's core operational and financial data, and their delegate boundaries are tight enough (costing feeds sales quoting, inventory feeds manufacturing) that designing them in isolation risks drawing those boundaries badly.

### Costing Agent
```
capability: costing_agent
allowed_actions:   [costing.calculate (applies existing approved formulas), costing.explain_formula, costing.propose_formula_change]
forbidden_actions: [costing.modify_formula_direct, *]
requires_approval: [costing.propose_formula_change]
classification_ceiling: confidential   # pricing/costing formulas are confidential-by-default per Phase 9
```
Mostly read/explain — applying an already-approved formula is informational and needs no approval; *changing* a formula routes through ERP Knowledge Engine's business-memory approval path (Phase 3/9). Delegates quote requests to Sales Agent.

### Accounting Agent
```
capability: accounting_agent
allowed_actions:   [accounting.read_ledger, accounting.explain_entry, accounting.propose_entry]
forbidden_actions: [accounting.write_ledger_direct, accounting.close_period, *]
requires_approval: [accounting.propose_entry]   # always, regardless of impact size
classification_ceiling: confidential
```
The most conservative of the business agents by nature — real financial records carry audit and regulatory weight beyond internal governance. Every entry proposal requires approval, no impact-size exception. Explicitly defers regulatory, tax, and audit judgment calls to a human accountant rather than presenting itself as authoritative on them — the same posture a careful assistant takes on legal or financial advice generally.

### Inventory Agent
```
capability: inventory_agent
allowed_actions:   [inventory.read_stock, inventory.propose_adjustment, inventory.propose_reorder]
forbidden_actions: [inventory.write_stock_direct, *]
requires_approval: [inventory.propose_adjustment, inventory.propose_reorder above a threshold quantity]
classification_ceiling: internal
```
Delegates anything about *why* stock is being consumed (a production run) to Manufacturing Agent; owns *what's on hand and what needs reordering* itself.

---

## Phase 15 — Operations Agents

### Manufacturing Agent
```
capability: manufacturing_agent
allowed_actions:   [manufacturing.explain_workflow, manufacturing.propose_schedule_change, manufacturing.flag_constraint]
forbidden_actions: [manufacturing.execute_schedule_direct, *]
requires_approval: [manufacturing.propose_schedule_change]
classification_ceiling: internal
```
Draws on ERP Knowledge Engine's workflow knowledge (Phase 9); flags material/capacity constraints against Inventory Agent's domain data. The eventual delegate target for Cutlist Optimization Agent (Phase 17) once built — worth naming now even though that agent doesn't exist yet.

### Sales Agent
```
capability: sales_agent
allowed_actions:   [sales.explain_status, sales.propose_quote, sales.propose_order_change]
forbidden_actions: [sales.execute_order_direct, sales.access_full_customer_pii_unscoped, *]
requires_approval: [sales.propose_quote, sales.propose_order_change]
classification_ceiling: internal
pii_handling: customer PII is tagged as its own dimension, separate from internal/confidential — Sales Agent gets scoped, minimum-necessary fields per task, never blanket access
```
The first agent to genuinely need a PII-aware classification dimension rather than just internal/confidential — customer personal data is a distinct legal category from business-confidential data in most jurisdictions, and treating it as just another point on the same scale would understate what's actually at stake. Pulls costing output from Costing Agent when drafting quotes.

### Project Management Agent
```
capability: project_management_agent
allowed_actions:   [pm.explain_status, pm.propose_milestone_update, pm.flag_at_risk]
forbidden_actions: [pm.close_project_direct, *]
requires_approval: [pm.propose_milestone_update]
classification_ceiling: internal
```
Distinctive in reasoning over two kinds of "project": customer-facing ERP projects *and* the orchestration layer's own task history (Task Manager's `task_event` log, Phase 2) — meaning it can explain both "why is this customer project behind schedule" and "why did this AI task take so long," a slightly meta capability none of the other agents have.

---

## Phase 16 — Code-Quality Agents

The natural first consumers of Code Analysis Engine (Phase 11).

### Code Review Agent
```
capability: code_review_agent
allowed_actions:   [review.analyze_diff, review.flag_concern, review.approve_recommendation]
forbidden_actions: [review.merge, review.override_human_approval, *]
requires_approval: none — its own output is advisory, feeding INTO approval rather than bypassing it
classification_ceiling: internal (structural tier); confidential raw-source follows Phase 11's gated path
```
Reviews any agent's proposed Git Manager MR using Code Analysis Engine's call graph — e.g. checking whether a change breaks a caller elsewhere — before a human sees it. Its assessment becomes an additional input to the Human Approval Layer request, not a replacement for the human's judgment.

### Reverse Engineering Agent
```
capability: reverse_engineering_agent
allowed_actions:   [reverse_eng.explain_undocumented, reverse_eng.propose_documentation_draft]
forbidden_actions: [reverse_eng.modify_code_direct, *]
requires_approval: [reverse_eng.propose_documentation_draft]
classification_ceiling: internal
note: output is explicitly labeled inferred/reconstructed, never presented with the confidence of documented fact
```
Reconstructs an explanation of undocumented code from structure and usage patterns rather than stated documentation — likely relevant given a large ERP with legacy customizations. A confirmed-accurate draft feeds back into Documentation Engine (Phase 9) as real documentation, closing the loop from inference to record.

### Architecture Agent
```
capability: architecture_agent
allowed_actions:   [architecture.explain_existing, architecture.propose_decision]
forbidden_actions: [architecture.implement_direct, *]
requires_approval: [architecture.propose_decision]
classification_ceiling: internal
output_requirement: every proposal must address why / alternatives / trade-offs / security / performance / scalability / complexity
```
The delegate target Django Agent and Database Agent already point to for schema/architecture questions (Phases 5/7/10). Its own proposals are required to meet the same seven-question rationale standard this entire roadmap has held itself to — the system holding its future decisions to the standard a human architect held this one.

---

## Phase 17 — Engineering & Calculation Agents

**Shared design principle across all three:** none of them let the model assert a numeric or layout result from its own generation. Language models are a known weak point for arithmetic and combinatorial optimization; every calculation here routes through an actual deterministic function or solver, executed via Shell Executor's sandbox, with the agent explaining the result rather than computing it in free text.

### Calculation Agent
```
capability: calculation_agent
allowed_actions:   [calc.apply_formula (via sandboxed execution), calc.explain_formula]
forbidden_actions: [calc.assert_unverified_number, *]
requires_approval: none for read/calculate — results are deterministic; only formula CHANGES (via Phase 9's annotation path) require approval
classification_ceiling: internal
integrity_requirement: numeric results must come from executed code, never asserted directly by the model
```

### Cutlist Optimization Agent
```
capability: cutlist_optimization_agent
allowed_actions:   [cutlist.gather_parameters, cutlist.run_optimizer (via sandboxed solver), cutlist.explain_result]
forbidden_actions: [cutlist.generate_layout_direct, *]
requires_approval: only if the resulting cutlist feeds a downstream production-schedule change
classification_ceiling: internal
integrity_requirement: layout results come from an actual optimization solver (bin-packing/cutting-stock algorithm), never asserted by the model
```
Its job is gathering the real input parameters through conversation, then invoking a real solver — not generating a cutlist as free text.

### AutoCAD Agent
```
capability: autocad_agent
allowed_actions:   [autocad.explain_drawing (via converted, parsed representation), autocad.propose_annotation]
forbidden_actions: [autocad.modify_drawing_direct, *]
requires_approval: [autocad.propose_annotation]
classification_ceiling: internal
known_constraint: AutoCAD's native format and tooling aren't Linux-native; this phase assumes a DWG→DXF conversion step (an open format) rather than live AutoCAD API access — worth revisiting if native integration is later required, given the stack's Ubuntu Linux base
```
Named honestly as a real constraint rather than assumed away — the only agent in this roadmap with a genuine platform-compatibility caveat baked into its design.

---

## Phase 18 — Cross-Cutting Agents

### Python Agent
```
capability: python_agent
allowed_actions:   [python.explain_code, python.propose_script, python.propose_change]
forbidden_actions: [python.execute_direct — routes through Shell Executor's normal gated path, *]
requires_approval: [python.propose_change]
classification_ceiling: internal
routing_note: checks first whether a request is actually Odoo- or Django-specific and delegates rather than attempting generically
```
The agent most likely to receive a request that's really in another agent's lane, since "Python" spans both named platforms — its template is built to actively check and hand off rather than default to answering.

### Documentation Agent
```
capability: documentation_agent
allowed_actions:   [docs.answer_from_existing, docs.propose_new_doc]
forbidden_actions: [docs.publish_direct, *]
requires_approval: [docs.propose_new_doc]
classification_ceiling: internal
boundary_note: works from existing written sources; Reverse Engineering Agent (Phase 16) is the delegate target when nothing is written down at all
```

### Security Agent
```
capability: security_agent
allowed_actions:   [security.review_change, security.explain_risk, security.audit_query (read-only)]
forbidden_actions: [security.modify_policy_direct, security.grant_permission, *]
requires_approval: none for its own advisory output — same relationship Code Review Agent has to actual merges
classification_ceiling: internal — audit access is itself classification-scoped, no blanket visibility
note: purely advisory; has no special authority over Security Layer's actual enforcement despite the shared name
```
Worth stating plainly: this agent recommending something is not Security Layer authorizing it. The name doesn't grant it elevated trust.

### Research Agent
```
capability: research_agent
allowed_actions:   [research.synthesize_internal, research.propose_external_lookup]
forbidden_actions: [research.access_external_direct, *]
requires_approval: [research.propose_external_lookup]   # always — external access is opt-in, not default
classification_ceiling: internal
note: default posture is internal-knowledge-only; external access requires the same explicit approval any external-model release does
```
The name suggests an agent that naturally reaches outward — the design has to actively resist that pull to stay consistent with the project's offline-first, privacy-first stance.

---
---

# Part C — Deployment & Resilience

## Phase 19 — Deployment Architecture · Docker Deployment

**Why single-host Docker Compose, not Kubernetes:** matches the stated stack exactly (Docker + Docker Compose named explicitly, not K8s), keeps operational complexity proportional to what reads as a single company's internal deployment, and satisfies offline-first/self-hosted priorities without needing a K8s control plane. Kubernetes is a noted future extension if the company needs multi-host scale or already has K8s operations expertise; Docker Swarm was considered as a middle ground and not chosen, since Compose already covers single-host well.

**Topology decisions worth naming explicitly:**
- Every module gets its own container — heavier operationally than grouping tightly-coupled modules (e.g. the Phase 1 governance trio) into one process, but more consistent with "modular, replaceable" as a stated top-level priority
- Four Docker networks, not one: `public` (Gateway only), `internal` (everything else), `data-net` (databases, reached only by Database Connector or direct app connections), `model-net` (Ollama, reached only by Reasoning Engine) — mirrors Phase 6's "no network by default" sandboxing principle at the deployment-topology level, not just inside individual sandboxed executions
- Secrets mounted via Docker secrets from the host's own secret store (SOPS+age or Vault, per Phase 2), never baked into images or passed as plain compose environment variables

```yaml
version: "3.9"

services:
  # Governance
  security-layer:
    build: ./governance/security
    networks: [internal]
    secrets: [db_password, jwt_signing_key]
    restart: unless-stopped

  audit-logger:
    build: ./governance/audit
    networks: [internal]
    depends_on: [postgres]
    restart: unless-stopped

  approval-layer:
    build: ./governance/approval
    networks: [internal]
    depends_on: [audit-logger]
    restart: unless-stopped

  # Platform spine
  config-manager:
    build: ./platform/config_manager
    networks: [internal]
    volumes: ["./config/policies:/app/policies:ro"]
    restart: unless-stopped

  gateway:
    build: ./platform/gateway
    networks: [internal, public]
    ports: ["8443:8443"]           # the ONLY externally exposed service
    depends_on: [security-layer, task-manager]
    restart: unless-stopped

  task-manager:
    build: ./platform/task_manager
    networks: [internal]
    depends_on: [postgres, security-layer]
    restart: unless-stopped

  # Knowledge substrate
  memory-manager:
    build: ./knowledge/memory_manager
    networks: [internal]
    depends_on: [postgres]
    restart: unless-stopped

  vector-search:
    build: ./knowledge/vector_search
    networks: [internal]
    depends_on: [postgres]          # pgvector extension, same instance
    restart: unless-stopped

  # Assembly + reasoning
  context-builder:
    build: ./assembly/context_builder
    networks: [internal]
    depends_on: [memory-manager, vector-search, security-layer]
    restart: unless-stopped

  prompt-builder:
    build: ./assembly/prompt_builder
    networks: [internal]
    restart: unless-stopped

  reasoning-engine:
    build: ./agents/reasoning_engine
    networks: [internal, model-net]
    depends_on: [context-builder, prompt-builder, ollama]
    restart: unless-stopped

  # Execution — internal network ONLY, never public
  shell-executor:
    build: ./execution/shell_executor
    networks: [internal]
    volumes: ["/var/run/docker.sock:/var/run/docker.sock:ro"]   # container-per-execution sandboxing
    depends_on: [security-layer]
    restart: unless-stopped

  git-manager:
    build: ./execution/git_manager
    networks: [internal]
    depends_on: [shell-executor]
    restart: unless-stopped

  database-connector:
    build: ./data/database_connector
    networks: [internal, data-net]
    secrets: [db_password]
    depends_on: [security-layer]
    restart: unless-stopped

  # Planning
  planner:
    build: ./planning/planner
    networks: [internal]
    depends_on: [reasoning-engine, capability-registry]
    restart: unless-stopped

  capability-registry:
    build: ./planning/capability_registry
    networks: [internal]
    volumes: ["./agents:/app/agents:ro"]   # reads every agent's capability.yaml
    restart: unless-stopped

  # Local inference
  ollama:
    image: ollama/ollama:latest
    networks: [model-net]
    volumes: ["ollama-models:/root/.ollama"]
    # GPU block below is optional — omit entirely for CPU-only hosts, offline-first must not assume GPU
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: ["gpu"]
    restart: unless-stopped

  # Data tier
  postgres:
    image: pgvector/pgvector:pg16
    networks: [internal, data-net]
    volumes: ["pg-data:/var/lib/postgresql/data"]
    secrets: [db_password]
    restart: unless-stopped

  mysql:
    image: mysql:8
    networks: [data-net]
    volumes: ["mysql-data:/var/lib/mysql"]
    secrets: [db_password]
    restart: unless-stopped

networks:
  public: {}
  internal: {}
  data-net: {}
  model-net: {}

volumes:
  pg-data:
  mysql-data:
  ollama-models:

secrets:
  db_password:
    file: ./secrets/db_password.txt        # SOPS/age-encrypted at rest on the host
  jwt_signing_key:
    file: ./secrets/jwt_signing_key.txt
```

This is a skeleton, not every one of the twenty-plus agents gets its own compose entry — but the pattern (one container, `internal` network, no ports unless it's Gateway) is what extends. Illustrative only; real secret values, resource limits, and image registries are an implementation-time decision.

---

## Phase 20 — Backup Strategy · Disaster Recovery

**What actually needs backing up, and at what priority:**

| Data | Priority | Note |
|---|---|---|
| Audit log (Phase 1) | Highest | Hash-chained — a restore must verify the chain is intact, not just that rows exist. A backup that silently drops the tail defeats the tamper-evidence design entirely |
| Business memory, decision/architecture history (Phase 3) | High | Append-only, compliance-relevant |
| Task, subtask, config (Phases 2, 8) | Medium | Operational state, recoverable but disruptive to lose |
| Vector embeddings, ERP knowledge (Phases 3, 9) | Medium | Re-derivable by re-ingestion, but re-ingestion takes real time |
| Short-term / working memory (Phase 3) | None | Designed to be lossy already — not worth backing up |
| Secrets | Separate, stricter process | Backed up via the secrets backend's own mechanism (e.g. Vault snapshot), never lumped in with database backups |
| Ollama model weights | Low | Large but re-downloadable from the public model registry — explicitly not worth the same backup priority as anything above |

**Disaster recovery principles:**
- RTO/RPO targets should be set per tier above by the company, not asserted here as fact — the table's priority ordering is the input to that decision, not a substitute for it
- DR runbooks are human-executed with the orchestration layer itself assumed unavailable during recovery — this system cannot be its own disaster-recovery mechanism; ordinary infrastructure DR practice applies underneath it, the same way any other production system needs a human-run recovery path
- Restore testing, not just backup existence — a backup that's never been test-restored is unverified. Periodic restore drills should specifically include verifying the audit log's hash chain post-restore, given how much of this design's trust model depends on that chain being genuinely unbroken

---
---

# Part D — Consolidated Reference

Closing out the remaining named deliverables from the original twenty by pulling together what's been distributed across all eleven prior phase documents plus Phases 12–20 above.

## Component Diagram

```
                              ┌─────────────┐
                              │   Gateway    │  ← only public-facing service
                              └──────┬───────┘
                                     │
                      ┌──────────────┼──────────────┐
                      ▼                              ▼
              ┌───────────────┐            ┌──────────────────────┐
              │ Task Manager  │            │ Security Layer /       │
              │               │◄──────────►│ Audit Logger /          │
              └───────┬───────┘            │ Human Approval Layer     │
                      │                     └───────────┬───────────┘
                      ▼                                  │ (authorizes everything below)
              ┌───────────────┐                          │
              │    Planner    │◄─────────────────────────┤
              │ + Capability  │                          │
              │   Registry    │                          │
              └───────┬───────┘                          │
                      ▼                                  │
        ┌─────────────────────────┐                      │
        │ Context Builder /        │◄─────────────────────┤
        │ Prompt Builder            │                      │
        └────────────┬──────────────┘                     │
                      ▼                                    │
        ┌─────────────────────────┐                        │
        │   Reasoning Engine        │◄───────────────────────┤
        │   (Ollama-backed)          │                        │
        └────────────┬────────────────┘                       │
     ┌────────────────┼────────────────┬─────────────┐         │
     ▼                ▼                ▼             ▼         │
┌─────────┐    ┌──────────────┐  ┌───────────┐  ┌──────────┐   │
│ 22 Agents│   │Shell Executor │  │Git Manager│  │ Database │◄──┘
│          │   │               │  │           │  │Connector │
└────┬─────┘   └───────────────┘  └───────────┘  └────┬─────┘
     ▼                                                  ▼
┌───────────────────────────┐                 ┌──────────────────┐
│ Memory Manager /            │                 │ PostgreSQL/MySQL  │
│ Vector Search                │◄────────────────┤ (via schema read) │
└──────────────┬──────────────┘                 └──────────────────┘
               ▲
┌──────────────┴───────────────────────┐
│ Documentation Engine / ERP Knowledge   │
│ Engine / Code Analysis Engine           │
└─────────────────────────────────────────┘

Cross-cutting, touching everything above:
Configuration Manager · Metrics Dashboard · Health Monitor · MCP Client · Plugin System
```

## Consolidated Folder Structure

```
ai-orchestration-layer/
├── governance/               # Phase 1  — security, audit, approval
├── platform/                  # Phase 2  — config, gateway, task manager
├── knowledge/                   # Phase 3  — memory manager, vector search
├── assembly/                     # Phase 4  — context builder, prompt builder
├── agents/                         # Phase 5, 10, 14–18 — reasoning_engine/ + every agent's capability.yaml + template.md
├── execution/                        # Phase 6  — shell executor, git manager
├── data/                               # Phase 7  — database connector
├── planning/                             # Phase 8  — planner, capability registry
├── knowledge_pipelines/                    # Phase 9, 11 — documentation, ERP knowledge, code analysis
├── extensibility/                            # Phase 12 — mcp_client/, plugin_system/
├── observability/                              # Phase 13 — health_monitor/, metrics_dashboard/
├── deploy/                                       # Phase 19 — docker-compose.yml, per-service Dockerfiles
├── config/                                         # policy YAML, non-secret configuration
├── secrets/                                          # gitignored — SOPS/age-encrypted references only
└── docs/                                               # this entire phase-by-phase design record
```

## API Surface Index

| Module | Base path | Phase |
|---|---|---|
| Security Layer | `/security/*` | 1 |
| Audit Logger | `/audit/*` | 1 |
| Human Approval Layer | `/approval/*` | 1 |
| Configuration Manager | `/config/*` | 2 |
| Gateway | `/api/v1/*` | 2 |
| Memory Manager | `/memory/*` | 3 |
| Vector Search | `/vector/*` | 3 |
| Context Builder | `/context/*` | 4 |
| Prompt Builder | `/prompt/*` | 4 |
| Reasoning Engine | `/reasoning/*` | 5 |
| Shell Executor | `/shell/*` | 6 |
| Git Manager | `/git/*` | 6 |
| Database Connector | `/db/*` | 7 |
| Planner | `/planner/*` | 8 |
| Capability Registry | `/capabilities/*` | 8 |
| Documentation Engine | `/docs/*` | 9 |
| ERP Knowledge Engine | `/erp-knowledge/*` | 9 |
| Code Analysis Engine | `/code-analysis/*` | 11 |
| MCP Client | `/mcp/*` | 12 |
| Plugin System | `/plugins/*` | 12 |
| Health Monitor | `/health/*` | 13 |
| Metrics Dashboard | `/metrics/*` | 13 |

## Database Schema Index

| Tables | Owning module | Phase |
|---|---|---|
| `role`, `role_permission`, `audit_event`, `approval_request` | Security / Audit / Approval | 1 |
| `task`, `task_event`, `config_override` | Task Manager / Config | 2 |
| `memory_record`, `decision_record`, `document`, `chunk` | Memory Manager / Vector Search | 3 |
| `context_package`, `context_item`, `prompt_template`, `prompt_render_log` | Context / Prompt Builder | 4 |
| `reasoning_execution`, `reasoning_step`, `agent_capability_def` | Reasoning Engine | 5 |
| `sandbox_execution`, `git_action`, `capability_command_allowlist` | Shell Executor / Git Manager | 6 |
| `db_query_log`, `db_dry_run`, `db_write`, `db_migration_request` | Database Connector | 7 |
| `task_graph`, `subtask`, `capability_registry_entry` | Planner | 8 |
| `doc_source`, `doc_ingestion_log`, `erp_schema_snapshot`, `erp_field_annotation`, `erp_formula` | Documentation / ERP Knowledge | 9 |
| `code_symbol`, `call_edge`, `raw_source_request`, `analysis_run` | Code Analysis Engine | 11 |

## Agent Communication Protocol

Agents never call each other directly. All inter-agent communication is mediated by Task Manager (task/subtask state) and Planner (routing). An agent signals a need for another agent via `delegate_to` in its structured output; Planner interprets that signal and creates a new subtask routed to the named capability. This indirection is deliberate: every handoff is visible in Task Manager's persisted state and Audit Logger's trace rather than a hidden direct call, and agents can be added, removed, or modified without any other agent's code changing — only Capability Registry and Planner's routing logic need to know an agent exists.

## Canonical Message Format

```json
{
  "reasoning": "string — the agent's explanation of its thinking",
  "answer_or_proposal": "string or structured object — the actual output",
  "confidence": "float, 0-1",
  "provenance": ["context_item references, Phase 4"],
  "risk_classification": "informational | low | medium | high",
  "delegate_to": "capability name, or null"
}
```
Domain-specific extensions layer on top where needed — e.g. `impact_estimate` for any data-touching agent (Phase 7).

## Sample Configuration File

```yaml
# config/system.yaml — loaded by Configuration Manager, Phase 2
# Illustrative only — real values are a company policy decision, not asserted here.
environment: production
classification_default: internal
model_routing:
  default_local_model: qwen-coder
  fallback_local_model: deepseek-coder
  external_model_allowed: false        # flipped only per-task via explicit approval
approval:
  default_timeout_minutes: 1440         # 24h — expires to rejected, per Phase 1
audit:
  retention_days:
    default: 365
    financial_business_memory: 2555     # ~7 years, illustrative — set to actual regulatory requirement
```

---

## Roadmap Complete

Phases 1–21 now cover every module and agent named in the original mandate (with the ERP Agent / Odoo Agent question still open, per the note at the top), plus deployment, backup/DR, and the consolidated reference deliverables. Any individual phase above can be pulled out and expanded to the same full depth as Phases 1–11 on request — this file trades some of that depth for completeness in one place, per the request to consolidate.
