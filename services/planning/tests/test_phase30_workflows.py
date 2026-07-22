import os

import pytest

from planning.db import SessionLocal
from planning import clients
from planning.planner import store
from planning.workflows import api as workflows_api, store as workflow_store, dispatcher

_REPO_WORKFLOWS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "workflows",
)


@pytest.fixture(autouse=True)
def real_workflows_dir(monkeypatch):
    """Every test in this file reads the real, checked-in
    workflows/code_review_pipeline.yaml — no fixture-only test doubles for
    the workflow definition itself, since a real, working example is the
    whole point of this phase."""
    monkeypatch.setattr(workflow_store, "WORKFLOWS_DIR", _REPO_WORKFLOWS_DIR)


def _fake_execution(status="completed", execution_id="fake-exec-1"):
    return {"id": execution_id, "status": status, "result": {}}


def test_list_workflows_finds_the_real_code_review_pipeline():
    result = workflows_api.list_workflows()
    names = {wf["workflow"] for wf in result["workflows"]}
    assert "code_review_pipeline" in names


def test_get_workflow_unknown_name_raises():
    with pytest.raises(workflow_store.WorkflowNotFound):
        workflow_store.get_workflow("definitely-not-a-real-workflow")


def test_list_workflows_not_configured_without_workflows_dir(monkeypatch):
    monkeypatch.setattr(workflow_store, "WORKFLOWS_DIR", None)
    with pytest.raises(workflow_store.WorkflowNotConfigured):
        workflow_store.list_workflows()


def test_trigger_endpoint_for_unknown_workflow_is_a_real_404(platform_url):
    db = SessionLocal()
    with pytest.raises(Exception) as exc_info:
        workflows_api.trigger_workflow("definitely-not-a-real-workflow", workflows_api.TriggerRequest(), db)
    db.close()
    assert exc_info.value.status_code == 404


def test_trigger_dispatches_the_whole_chain_when_every_step_completes_synchronously(platform_url, monkeypatch):
    """Every one of code_review_pipeline's 3 steps "completes" on its first
    call — dispatch_ready_subtasks must chase the whole dependency chain
    (review -> test -> summarize) in one trigger call, not just the first
    wave of ready steps."""
    monkeypatch.setattr(clients, "execute_reasoning", lambda *a, **kw: _fake_execution("completed"))

    db = SessionLocal()
    run = workflows_api.trigger_workflow("code_review_pipeline", workflows_api.TriggerRequest(), db)
    db.close()

    assert run["workflow"] == "code_review_pipeline"
    statuses = {s["subtask_id"]: s["status"] for s in run["subtasks"]}
    assert statuses == {"review": "done", "test": "done", "summarize": "done"}


def test_trigger_only_dispatches_ready_steps_when_the_first_step_pauses(platform_url, monkeypatch):
    """The real, load-bearing case: review pauses for human approval, so
    test and summarize (both depend on it) must stay "planned" — never
    dispatched early, since that would batch consent no step actually
    granted yet."""
    monkeypatch.setattr(clients, "execute_reasoning", lambda *a, **kw: _fake_execution("awaiting_approval", "exec-review-1"))

    db = SessionLocal()
    run = workflows_api.trigger_workflow("code_review_pipeline", workflows_api.TriggerRequest(), db)
    db.close()

    statuses = {s["subtask_id"]: s["status"] for s in run["subtasks"]}
    assert statuses == {"review": "awaiting_approval", "test": "planned", "summarize": "planned"}
    review = next(s for s in run["subtasks"] if s["subtask_id"] == "review")
    assert review["reasoning_execution_id"] == "exec-review-1"


def test_advance_resumes_an_approved_step_and_dispatches_what_it_unblocks(platform_url, monkeypatch):
    """The real continuation path: review was awaiting_approval, a human
    approved it (simulated here by resume_reasoning now returning
    "completed"), so advance() must both flip review to done AND dispatch
    test (newly unblocked) in the same call."""
    monkeypatch.setattr(clients, "execute_reasoning", lambda *a, **kw: _fake_execution("awaiting_approval", "exec-review-1"))
    db = SessionLocal()
    run = workflows_api.trigger_workflow("code_review_pipeline", workflows_api.TriggerRequest(), db)
    db.close()
    graph_id = run["task_graph_id"]

    monkeypatch.setattr(clients, "resume_reasoning", lambda execution_id: _fake_execution("completed", execution_id))
    monkeypatch.setattr(clients, "execute_reasoning", lambda *a, **kw: _fake_execution("completed", "exec-test-1"))

    db = SessionLocal()
    advanced = workflows_api.advance_run(graph_id, workflows_api.TriggerRequest(), db)
    db.close()

    statuses = {s["subtask_id"]: s["status"] for s in advanced["subtasks"]}
    assert statuses["review"] == "done"
    assert statuses["test"] == "done"  # newly unblocked and dispatched in the same advance() call


def test_advance_on_a_still_pending_approval_is_a_safe_no_op(platform_url, monkeypatch):
    """Mirrors reasoning_engine/loop.py's own resume() semantics: calling
    advance() before a human has actually decided the approval must not
    change anything — matches the dispatcher's whole design rationale for
    calling resume_reasoning() unconditionally rather than pre-checking
    approval status itself."""
    monkeypatch.setattr(clients, "execute_reasoning", lambda *a, **kw: _fake_execution("awaiting_approval", "exec-review-1"))
    db = SessionLocal()
    run = workflows_api.trigger_workflow("code_review_pipeline", workflows_api.TriggerRequest(), db)
    db.close()
    graph_id = run["task_graph_id"]

    monkeypatch.setattr(clients, "resume_reasoning", lambda execution_id: _fake_execution("awaiting_approval", execution_id))

    db = SessionLocal()
    advanced = workflows_api.advance_run(graph_id, workflows_api.TriggerRequest(), db)
    db.close()

    statuses = {s["subtask_id"]: s["status"] for s in advanced["subtasks"]}
    assert statuses == {"review": "awaiting_approval", "test": "planned", "summarize": "planned"}
    assert advanced["advanced"] == []


def test_trigger_marks_a_failed_step_failed_and_never_dispatches_its_dependents(platform_url, monkeypatch):
    monkeypatch.setattr(clients, "execute_reasoning", lambda *a, **kw: _fake_execution("refused", "exec-review-1"))

    db = SessionLocal()
    run = workflows_api.trigger_workflow("code_review_pipeline", workflows_api.TriggerRequest(), db)
    db.close()

    statuses = {s["subtask_id"]: s["status"] for s in run["subtasks"]}
    assert statuses == {"review": "failed", "test": "planned", "summarize": "planned"}


def test_get_run_returns_the_persisted_graph(platform_url, monkeypatch):
    monkeypatch.setattr(clients, "execute_reasoning", lambda *a, **kw: _fake_execution("completed"))
    db = SessionLocal()
    run = workflows_api.trigger_workflow("code_review_pipeline", workflows_api.TriggerRequest(), db)
    db.close()

    db = SessionLocal()
    fetched = workflows_api.get_run(run["task_graph_id"], db)
    db.close()
    assert fetched["task_graph_id"] == run["task_graph_id"]
    assert len(fetched["subtasks"]) == 3


def test_live_trigger_of_the_real_code_review_pipeline(governance_url, agents_url, platform_url, ollama_available):
    """
    One real, live end-to-end test — no monkeypatching. Triggers the
    actual code_review_pipeline.yaml against real capabilities
    (code_review_agent, testing_agent, architecture_agent) through real
    Reasoning Engine execution. Lenient about the exact terminal status
    each step reaches (a live model's own refusal/approval/success
    pathway isn't deterministic run to run) — this proves the real
    dispatch wiring works end to end, not that every step succeeds.
    """
    if not ollama_available:
        pytest.skip("Ollama not reachable at OLLAMA_URL")

    db = SessionLocal()
    run = workflows_api.trigger_workflow(
        "code_review_pipeline",
        workflows_api.TriggerRequest(correlation_id="phase30-live-test"),
        db,
    )
    db.close()

    assert run["task_graph_id"]
    review = next(s for s in run["subtasks"] if s["subtask_id"] == "review")
    assert review["status"] in ("done", "awaiting_approval", "failed")
    if review["status"] == "planned":
        pytest.fail("review has no depends_on — it must have been dispatched immediately, never left planned")
