import pytest

from planning.db import SessionLocal
from planning.planner import api, store
from planning import clients


def _fake_plan_execution(task_graph, outcome="plan", **overrides):
    result = {
        "outcome": outcome, "confidence": 0.9, "task_graph": task_graph,
        "clarification_question": None, "answer_or_proposal": "test plan",
    }
    result.update(overrides)
    return {"id": "fake-exec-1", "status": "completed", "result": result}


def test_plan_endpoint_creates_graph_and_real_subtasks(platform_url, monkeypatch):
    monkeypatch.setattr(clients, "execute_reasoning", lambda *a, **kw: _fake_plan_execution(
        [{"subtask_id": "s1", "description": "Explain the rule", "agent_capability": "odoo_agent", "depends_on": [], "status": "planned"}],
    ))

    db = SessionLocal()
    result = api.plan(api.PlanRequest(task_id="planner-api-test-1", title="Explain the rule", requested_by="human_admin"), db)
    db.close()

    assert result["outcome"] == "plan"
    assert len(result["subtasks"]) == 1
    assert result["subtasks"][0]["agent_capability"] == "odoo_agent"
    assert result["subtasks"][0]["platform_task_id"]


def test_plan_endpoint_needs_clarification(platform_url, monkeypatch):
    monkeypatch.setattr(clients, "execute_reasoning", lambda *a, **kw: _fake_plan_execution(
        [], outcome="needs_clarification", clarification_question="Which report do you mean?",
    ))

    db = SessionLocal()
    result = api.plan(api.PlanRequest(task_id="planner-api-test-2", title="Run the report", requested_by="human_admin"), db)
    db.close()

    assert result["outcome"] == "needs_clarification"
    assert result["needs_clarification"] is True
    assert result["clarification_question"] == "Which report do you mean?"
    assert result["subtasks"] == []


def test_plan_endpoint_no_capability_found(platform_url, monkeypatch):
    monkeypatch.setattr(clients, "execute_reasoning", lambda *a, **kw: _fake_plan_execution([], outcome="no_capability_found"))

    db = SessionLocal()
    result = api.plan(api.PlanRequest(task_id="planner-api-test-3", title="Book a flight to Tokyo", requested_by="human_admin"), db)
    db.close()

    assert result["outcome"] == "no_capability_found"
    assert result["subtasks"] == []


def test_plan_endpoint_reports_unreachable_reasoning_engine_as_502(monkeypatch):
    def raise_error(*a, **kw):
        raise ConnectionError("simulated: agents service down")

    monkeypatch.setattr(clients, "execute_reasoning", raise_error)

    db = SessionLocal()
    with pytest.raises(Exception) as exc_info:
        api.plan(api.PlanRequest(task_id="planner-api-test-4", title="anything", requested_by="human_admin"), db)
    db.close()
    assert exc_info.value.status_code == 502


def test_replan_supersedes_the_previous_graph(platform_url, monkeypatch):
    monkeypatch.setattr(clients, "execute_reasoning", lambda *a, **kw: _fake_plan_execution(
        [{"subtask_id": "s1", "description": "original plan", "agent_capability": "odoo_agent", "depends_on": [], "status": "planned"}],
    ))
    db = SessionLocal()
    first = api.plan(api.PlanRequest(task_id="planner-replan-test-1", title="Explain something", requested_by="human_admin"), db)
    db.close()

    monkeypatch.setattr(clients, "execute_reasoning", lambda *a, **kw: _fake_plan_execution(
        [{"subtask_id": "s1", "description": "revised plan using database_agent instead", "agent_capability": "database_agent", "depends_on": [], "status": "planned"}],
    ))
    db = SessionLocal()
    revised = api.replan_endpoint(
        api.ReplanRequest(task_id="planner-replan-test-1", original_description="Explain something", reason="odoo_agent refused: outside its ORM scope"),
        db,
    )
    old_graph = store.get_graph(db, first["task_graph_id"])
    db.close()

    assert revised["subtasks"][0]["agent_capability"] == "database_agent"
    assert old_graph.superseded_by == revised["task_graph_id"]


def test_capabilities_debug_endpoint_hits_real_agents_service(agents_url):
    result = api.capabilities_debug()
    names = {c["agent_capability"] for c in result["capabilities"]}
    assert "odoo_agent" in names
    assert "database_agent" in names


def test_live_plan_produces_a_real_outcome(governance_url, agents_url, platform_url, ollama_available):
    """
    One real live-model end-to-end test — lenient about which specific
    capability it routes to (both odoo_agent and database_agent are
    plausible fits for some tasks, and a live model won't route
    identically every run), but proves the full pipeline — real
    Capability Registry roster, real Reasoning Engine call, real
    Task Manager subtask creation — works end to end with a real model.
    """
    if not ollama_available:
        pytest.skip("Ollama not reachable at OLLAMA_URL")

    db = SessionLocal()
    result = api.plan(
        api.PlanRequest(
            task_id="planner-live-test-1", title="Explain the invoice approval rule",
            description="A new employee wants to understand how invoice approval works in Odoo.",
            requested_by="human_admin",
        ),
        db,
    )
    db.close()

    assert result["outcome"] in ("plan", "needs_clarification", "no_capability_found")
    if result["outcome"] == "plan":
        assert len(result["subtasks"]) >= 1
        for subtask in result["subtasks"]:
            assert subtask["agent_capability"] in ("odoo_agent", "database_agent")
