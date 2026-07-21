# AIOS DB ERD (Logical, from ORM models)

This ERD is derived from the repo’s SQLAlchemy model files (tables named
by `__tablename__`). For the full schema index by owning module, see
[`aios-architecture-and-phases.md#phase-21-consolidated-reference`](aios-architecture-and-phases.md#phase-21-consolidated-reference).

This codebase uses **string IDs** and typically does not
enforce SQL `FOREIGN KEY` constraints; relationships here are inferred from
reference columns (e.g. `task_id`, `execution_id`, `document_id`, etc.).

## Entity list (tables)

- `audit_event`
- `approval_request`
- `approval_review`
- `test_execution_target`
- `task`
- `task_event`
- `config_override`
- `conversation` (Control UI chat threads)
- `memory_record`
- `decision_record`
- `document`
- `chunk`
- `context_package`
- `context_item`
- `pinned_fact`
- `prompt_template`
- `prompt_render_log`
- `reasoning_execution`
- `reasoning_step`
- `agent_capability_def`
- `sandbox_execution`
- `git_action`
- `db_query_log`
- `db_dry_run`
- `db_write`
- `db_migration_request`
- `task_graph`
- `subtask`
- `capability_registry_entry`
- `doc_source`
- `doc_ingestion_log`
- `erp_schema_snapshot`
- `erp_field_annotation`
- `erp_formula`
- `code_symbol`
- `call_edge`
- `raw_source_request`
- `analysis_run`
- `mcp_server`
- `mcp_invocation`
- `plugin`
- `alert_config`
- `health_poll_log`

## Logical ERD (Mermaid)

```mermaid
erDiagram
    TASK ||--o{ TASK_EVENT : "task_id"
    TASK ||--o{ REASONING_EXECUTION : "task_id"
    TASK ||--o{ SANDBOX_EXECUTION : "task_id"
    TASK ||--o{ DB_QUERY_LOG : "task_id"
    TASK ||--o{ DB_DRY_RUN : "task_id"
    TASK ||--o{ DB_WRITE : "task_id"
    TASK ||--o{ DB_MIGRATION_REQUEST : "task_id"
    TASK ||--o{ TASK_GRAPH : "task_id"
    TASK ||--o{ RAW_SOURCE_REQUEST : "task_id"
    TASK ||--o{ GIT_ACTION : "task_id"

    REASONING_EXECUTION ||--o{ REASONING_STEP : "execution_id"
    REASONING_STEP }o--|| PROMPT_RENDER_LOG : "prompt_ref"

    TASK_GRAPH }o--|| REASONING_EXECUTION : "reasoning_execution_id"
    TASK_GRAPH ||--o{ SUBTASK : "task_graph_id"

    AGENT_CAPABILITY_DEF ||--o{ REASONING_EXECUTION : "agent_capability"
    CAPABILITY_REGISTRY_ENTRY ||--o{ REASONING_EXECUTION : "agent_capability"

    CONTEXT_PACKAGE ||--o{ CONTEXT_ITEM : "context_package_id"

    CONTEXT_PACKAGE ||--o{ PROMPT_RENDER_LOG : "context_package_id"
    PROMPT_TEMPLATE ||--o{ PROMPT_RENDER_LOG : "template_id+version"

    DOCUMENT ||--o{ CHUNK : "document_id"

    DOC_SOURCE ||--o{ DOC_INGESTION_LOG : "doc_source_id"
    DOCUMENT ||--o{ DOC_INGESTION_LOG : "document_id"

    DB_DRY_RUN ||--o{ DB_WRITE : "dry_run_id"

    APPROVAL_REQUEST ||--o{ APPROVAL_REVIEW : "approval_id"
    REASONING_EXECUTION }o--|| APPROVAL_REQUEST : "approval_id"
    RAW_SOURCE_REQUEST }o--|| APPROVAL_REQUEST : "approval_id"
    CAPABILITY_REGISTRY_ENTRY }o--|| APPROVAL_REQUEST : "approval_id"
    PLUGIN }o--|| APPROVAL_REQUEST : "approval_id"
    MCP_SERVER }o--|| APPROVAL_REQUEST : "approval_id"

    MCP_SERVER ||--o{ MCP_INVOCATION : "server_id"
    TASK ||--o{ MCP_INVOCATION : "task_id (optional)"

    CODE_SYMBOL ||--o{ CALL_EDGE : "caller_symbol_id / callee_symbol_id"

    TASK }o--|| CONVERSATION : "conversation_id (threads turns)"

    CONFIG_OVERRIDE ||--o{ TASK : "service/key (applied config changes)"

    ALERT_CONFIG ||--o{ HEALTH_POLL_LOG : "polled & compared (no strict FK)"
```

