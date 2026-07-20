import httpx

from observability.metrics_dashboard import aggregator, api


def test_overview_returns_all_five_categories(full_stack):
    result = aggregator.overview()
    assert set(result.keys()) == set(aggregator.CATEGORIES)
    for name, payload in result.items():
        assert payload["category"] == name


def test_task_throughput_latency_reflects_a_real_completed_task(full_stack):
    resp = httpx.post(
        f"{full_stack['platform-spine']}/api/v1/tasks",
        json={"title": "metrics test task", "description": "test"},
        headers={"Authorization": "Bearer dev-admin-token"},
    )
    task_id = resp.json()["id"]
    for status in ("in_progress", "review", "done"):
        httpx.post(
            f"{full_stack['platform-spine']}/api/v1/tasks/{task_id}/status",
            json={"status": status},
            headers={"Authorization": "Bearer dev-admin-token"},
        )

    result = aggregator.task_throughput_latency()
    assert result["by_status"].get("done", 0) >= 1
    assert result["avg_latency_seconds_for_done"] is not None
    assert result["avg_latency_seconds_for_done"] >= 0
    assert result["partial"] is False


def test_task_throughput_latency_reports_partial_when_source_unreachable(monkeypatch):
    from observability import clients
    monkeypatch.setattr(clients, "get_tasks", lambda status=None: [])
    result = aggregator.task_throughput_latency()
    assert result["partial"] is True
    assert result["total"] == 0


def test_reasoning_iterations_reflects_a_real_completed_execution(full_stack, ollama_available):
    """
    Drives a real execution through the LIVE agents service over HTTP —
    observability's own test process can't import agents' Python modules
    to monkeypatch its model call the way agents' own tests do (separate
    service, separate package, not installed here), so this is a real
    live-model smoke test instead, same convention as the one genuine
    live-model test each other phase keeps.
    """
    if not ollama_available:
        import pytest
        pytest.skip("Ollama not reachable at OLLAMA_URL")

    # A freshly-started agents service registers odoo_agent's template as
    # pending_approval on startup (Phase 5) — approve it the same way
    # every other phase's tests do, over pure HTTP, rather than silently
    # skipping the common case of a fresh service.
    templates = httpx.get(f"{full_stack['assembly']}/prompt/templates").json()
    matching = [t for t in templates if t["agent_template_id"] == "odoo_agent"]
    if not any(t["status"] == "active" for t in matching) and matching:
        pending = next((t for t in matching if t["status"] == "pending_approval"), None)
        if pending:
            approvals = httpx.get(f"{full_stack['governance']}/approval/pending").json()
            approval = next((a for a in approvals if a["action"] == "prompt_template.register.odoo_agent"), None)
            if approval:
                httpx.post(f"{full_stack['governance']}/approval/{approval['id']}/decide", json={"decided_by": "human_admin", "approve": True})
                httpx.post(f"{full_stack['assembly']}/prompt/templates/reconcile-approvals")

    httpx.post(
        f"{full_stack['agents']}/reasoning/execute",
        json={
            "task_id": "metrics-reasoning-test-1", "task_description": "Explain, in one sentence, what a sale order is. Don't propose any changes.",
            "agent_capability": "odoo_agent", "namespace": "default", "target_model": "qwen3.5:4b", "max_iterations": 6,
        },
        timeout=60.0,
    )

    metrics = aggregator.reasoning_iterations()
    assert metrics["total_executions"] >= 1
    assert metrics["by_agent_capability"].get("odoo_agent", 0) >= 1
    assert metrics["partial"] is False


def test_approval_queue_reflects_real_pending_and_decided_requests(full_stack):
    pending_resp = httpx.post(f"{full_stack['governance']}/approval/request", json={"action": "odoo.propose_change", "requested_by": "odoo_agent"})
    decided_resp = httpx.post(f"{full_stack['governance']}/approval/request", json={"action": "odoo.propose_change", "requested_by": "odoo_agent"})
    decided_id = decided_resp.json()["id"]
    httpx.post(f"{full_stack['governance']}/approval/{decided_id}/decide", json={"decided_by": "human_admin", "approve": True})

    result = aggregator.approval_queue()
    assert result["pending_count"] >= 1
    assert result["decided_count"] >= 1
    assert result["avg_time_to_decision_seconds"] is not None
    assert result["avg_time_to_decision_seconds"] >= 0


def test_tool_execution_volume_reflects_real_shell_and_db_activity(full_stack, database_url):
    # A real, already-registered capability (database_agent) — an
    # invented capability name with no governance policy role would
    # fail-closed at authorize() before ever reaching the query log this
    # test wants to observe.
    resp = httpx.post(
        f"{database_url}/db/query",
        json={
            "target_db": "demo_erp", "table": "sale_order", "sql_template": "SELECT id FROM sale_order WHERE id = :id",
            "params": {"id": 1}, "capability": "database_agent", "requesting_agent": "test",
        },
    )
    assert resp.status_code == 200

    result = aggregator.tool_execution_volume()
    assert result["by_capability"].get("database_agent", {}).get("db", 0) >= 1
    assert result["partial"] is False


def test_classification_distribution_reflects_real_ingested_content(full_stack):
    httpx.post(
        f"{full_stack['knowledge']}/vector/ingest",
        json={"source": "metrics-test-doc", "content": "confidential test content for metrics", "project_id": "proj-metrics", "classification": "confidential"},
    )
    result = aggregator.classification_distribution()
    assert result["by_classification"].get("confidential", 0) >= 1
    assert result["partial"] is False


def test_export_endpoint_matches_overview_shape():
    export_result = api.export()
    overview_result = api.overview()
    assert set(export_result.keys()) == set(overview_result.keys())


def test_unknown_category_returns_404():
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        api.get_category("nonexistent_category")
    assert exc_info.value.status_code == 404
