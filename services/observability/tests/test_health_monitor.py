from observability.db import SessionLocal
from observability.health_monitor import api, checks, store
from observability.health_monitor.models import HealthPollLog
from observability import clients


def test_poll_health_reports_up_for_a_real_reachable_service(governance_url):
    result = clients.poll_health("governance", governance_url)
    assert result["status"] == "up"


def test_poll_health_reports_down_for_an_unreachable_service():
    result = clients.poll_health("nonexistent", "http://127.0.0.1:1")
    assert result["status"] == "down"


def test_health_system_aggregates_across_every_known_service_without_raising(full_stack):
    """A live full aggregate call — confirms one dead peer (extensibility
    and planning aren't started for this test) never blinds the rest of
    the response, matching the doc's own failure-handling requirement."""
    db = SessionLocal()
    result = api.health_system(db)
    db.close()

    assert "governance_reachable" in result
    assert result["governance_reachable"] is True
    names = {s["name"] for s in result["services"]}
    assert "governance" in names
    assert "agents" in names
    # extensibility/planning weren't started for this test — they must
    # show up as down, not crash the whole response
    assert any(s["name"] == "extensibility" and s["status"] == "down" for s in result["services"])


def test_health_system_records_a_poll_log(full_stack):
    db = SessionLocal()
    api.health_system(db)
    logs = db.query(HealthPollLog).all()
    db.close()
    assert len(logs) == 1
    assert isinstance(logs[0].services_down, list)
    assert isinstance(logs[0].gaps_found, list)


def test_check_stuck_tasks_finds_a_real_task_stuck_past_the_threshold(full_stack, monkeypatch):
    """Real Task Manager data — a task created and left in_progress, with
    the threshold monkeypatched down to 0 minutes so it's immediately
    'stuck' without needing to actually wait an hour."""
    import httpx
    resp = httpx.post(
        f"{full_stack['platform-spine']}/api/v1/tasks",
        json={"title": "a task that will get stuck", "description": "test"},
        headers={"Authorization": "Bearer dev-odoo-agent-token"},
    )
    task = resp.json()
    httpx.post(
        f"{full_stack['platform-spine']}/api/v1/tasks/{task['id']}/status",
        json={"status": "in_progress"},
        headers={"Authorization": "Bearer dev-odoo-agent-token"},
    )

    monkeypatch.setattr(checks, "STUCK_TASK_THRESHOLD_MINUTES", 0)
    stuck = checks.check_stuck_tasks()
    assert any(s["task_id"] == task["id"] for s in stuck)


def test_check_stuck_tasks_does_not_flag_a_fresh_task(full_stack):
    """The threshold is real (default 60 minutes) — a task created moments
    ago must NOT show up as stuck."""
    import httpx
    resp = httpx.post(
        f"{full_stack['platform-spine']}/api/v1/tasks",
        json={"title": "a fresh task", "description": "test"},
        headers={"Authorization": "Bearer dev-odoo-agent-token"},
    )
    task = resp.json()
    stuck = checks.check_stuck_tasks()
    assert not any(s["task_id"] == task["id"] for s in stuck)


def test_check_stale_erp_knowledge_finds_a_real_current_snapshot_via_the_real_endpoint(full_stack):
    """Confirms the real round trip through GET /erp-knowledge/snapshots
    (Phase 9's own store.mark_snapshot_stale only flips an EXISTING
    'current' row to 'stale' on a later failed sync — it never fabricates
    a stale row for a target that was never successfully synced in the
    first place, so a freshly-synced target here is honestly 'current',
    not 'stale'; the filtering-for-stale logic itself is covered next)."""
    import httpx
    httpx.post(f"{full_stack['knowledge_pipelines']}/erp-knowledge/sync", json={"target_db": "demo_erp"})
    snapshots = clients.get_erp_snapshots()
    assert any(s["target_db"] == "demo_erp" and s["status"] == "current" for s in snapshots)


def test_check_stale_erp_knowledge_filters_correctly(monkeypatch):
    """The filtering logic itself, tested against a synthetic response
    shape matching GET /erp-knowledge/snapshots' real, already-tested
    contract (services/knowledge_pipelines/tests/test_erp_knowledge_engine_api.py) —
    reproducing a genuine stale-flip live would need a sync that
    succeeds once and then fails on a second call against the same
    target, not reliably engineerable from outside that service."""
    def fake_get_erp_snapshots():
        return [
            {"target_db": "demo_erp", "status": "current", "synced_at": "2026-01-01T00:00:00+00:00"},
            {"target_db": "legacy_target", "status": "stale", "synced_at": "2026-01-01T00:00:00+00:00"},
        ]

    monkeypatch.setattr(clients, "get_erp_snapshots", fake_get_erp_snapshots)
    stale = checks.check_stale_erp_knowledge()
    assert {s["target_db"] for s in stale} == {"legacy_target"}


def test_check_stuck_reasoning_executions_finds_a_real_iteration_limit_failure(full_stack, monkeypatch):
    """
    Engineering agents' own execution service into a genuine
    iteration-exhaustion state via pure HTTP (no shared process, no
    direct model stubbing available across a service boundary) isn't a
    reliable trigger to build a test around. What IS observability's own
    to test honestly is checks.py's filtering logic against a real
    response *shape* from agents' GET /reasoning/executions — the
    endpoint itself is already verified for real in
    services/agents/tests/test_reasoning_engine.py. Monkeypatching
    clients.get_reasoning_executions (the actual boundary this module
    owns) rather than agents' internals is the honest seam here.
    """
    def fake_get_reasoning_executions(status=None, agent_capability=None):
        return [
            {
                "id": "exec-stuck-1", "task_id": "task-1", "agent_capability": "odoo_agent",
                "status": "failed", "iterations_used": 8, "max_iterations": 8,
                "failure_reason": "iteration_limit_exceeded", "created_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "id": "exec-normal-failure", "task_id": "task-2", "agent_capability": "odoo_agent",
                "status": "failed", "iterations_used": 1, "max_iterations": 8,
                "failure_reason": "model_unavailable", "created_at": "2026-01-01T00:00:00+00:00",
            },
        ]

    monkeypatch.setattr(clients, "get_reasoning_executions", fake_get_reasoning_executions)

    stuck = checks.check_stuck_reasoning_executions()
    stuck_ids = {s["execution_id"] for s in stuck}
    assert "exec-stuck-1" in stuck_ids
    assert "exec-normal-failure" not in stuck_ids  # a different, non-iteration-limit failure must not be flagged


def test_alert_config_persists_the_intent_only():
    db = SessionLocal()
    result = api.alert_config(
        api.AlertConfigRequest(metric_or_gap="stuck_tasks", threshold=60, destination_ref="slack:#ops-alerts (not wired)", created_by="human_admin"),
        db,
    )
    db.close()
    assert result["metric_or_gap"] == "stuck_tasks"
    assert result["destination_ref"] == "slack:#ops-alerts (not wired)"
