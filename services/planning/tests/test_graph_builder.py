from planning.db import SessionLocal
from planning.planner import graph_builder, store


def _completed_execution(result: dict, execution_id: str = "exec-1") -> dict:
    return {"id": execution_id, "status": "completed", "result": result}


def test_plan_outcome_creates_graph_and_real_subtasks(platform_url):
    db = SessionLocal()
    execution = _completed_execution({
        "outcome": "plan", "confidence": 0.9,
        "task_graph": [
            {"subtask_id": "s1", "description": "Explain the rule", "agent_capability": "odoo_agent", "depends_on": [], "status": "planned"},
        ],
    })
    result = graph_builder.build_graph_from_execution(db, "task-graph-test-1", execution)

    assert result["task_graph"].outcome == "plan"
    assert len(result["subtasks"]) == 1
    assert result["subtasks"][0].agent_capability == "odoo_agent"
    assert result["subtasks"][0].platform_task_id  # a real Task Manager task was created
    db.close()


def test_plan_outcome_with_multiple_dependent_subtasks(platform_url):
    db = SessionLocal()
    execution = _completed_execution({
        "outcome": "plan", "confidence": 0.8,
        "task_graph": [
            {"subtask_id": "s1", "description": "Read the data", "agent_capability": "database_agent", "depends_on": [], "status": "planned"},
            {"subtask_id": "s2", "description": "Explain it", "agent_capability": "odoo_agent", "depends_on": ["s1"], "status": "planned"},
        ],
    })
    result = graph_builder.build_graph_from_execution(db, "task-graph-test-2", execution)

    assert len(result["subtasks"]) == 2
    dependent = [s for s in result["subtasks"] if s.subtask_id == "s2"][0]
    assert dependent.depends_on == ["s1"]
    db.close()


def test_needs_clarification_outcome_creates_no_subtasks():
    db = SessionLocal()
    execution = _completed_execution({
        "outcome": "needs_clarification", "confidence": 0.5,
        "clarification_question": "Which invoice are you asking about?",
        "task_graph": [],
    })
    result = graph_builder.build_graph_from_execution(db, "task-graph-test-3", execution)
    db.close()

    assert result["task_graph"].outcome == "needs_clarification"
    assert result["task_graph"].needs_clarification is True
    assert result["task_graph"].clarification_question == "Which invoice are you asking about?"
    assert result["subtasks"] == []


def test_no_capability_found_outcome_creates_no_subtasks():
    db = SessionLocal()
    execution = _completed_execution({"outcome": "no_capability_found", "confidence": 0.9, "task_graph": []})
    result = graph_builder.build_graph_from_execution(db, "task-graph-test-4", execution)
    db.close()

    assert result["task_graph"].outcome == "no_capability_found"
    assert result["subtasks"] == []


def test_non_completed_execution_status_is_recorded_as_failed():
    db = SessionLocal()
    execution = {"id": "exec-2", "status": "refused", "result": {"denial_reason": "not permitted"}}
    result = graph_builder.build_graph_from_execution(db, "task-graph-test-5", execution)
    db.close()

    assert result["task_graph"].outcome == "failed"
    assert "refused" in result["reason"]


def test_unrecognized_outcome_value_is_recorded_as_failed():
    db = SessionLocal()
    execution = _completed_execution({"outcome": "something_unexpected", "task_graph": []})
    result = graph_builder.build_graph_from_execution(db, "task-graph-test-6", execution)
    db.close()

    assert result["task_graph"].outcome == "failed"


def test_reasoning_execution_id_is_preserved_for_traceability():
    db = SessionLocal()
    execution = _completed_execution({"outcome": "no_capability_found", "task_graph": []}, execution_id="exec-traceable")
    result = graph_builder.build_graph_from_execution(db, "task-graph-test-7", execution)
    db.close()
    assert result["task_graph"].reasoning_execution_id == "exec-traceable"
