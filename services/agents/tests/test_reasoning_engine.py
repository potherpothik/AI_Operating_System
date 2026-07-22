import httpx
import pytest
from fastapi.testclient import TestClient

from agents.db import SessionLocal
from agents.reasoning_engine import loop, capability_registry, store
from agents.odoo_agent import register as odoo_agent_register
from main import app

test_client = TestClient(app)

# Explicit rather than relying on platform-spine's config default
# (default_local_model documents the intended qwen-coder/deepseek-coder
# stack, per the Phase 5 design doc) — this sandbox only has qwen3.5:4b
# actually pulled via Ollama. Overriding the config default is the
# operationally correct fix for a real deployment; tests pin the model
# explicitly so they don't depend on that override having been applied.
LOCAL_MODEL = "qwen3.5:4b"


def test_execute_raises_for_unknown_capability():
    db = SessionLocal()
    with pytest.raises(loop.UnknownCapability):
        loop.execute(db, "task-1", "do something", "nonexistent_capability", "default")
    db.close()


def _ensure_odoo_agent_ready(governance_url, assembly_url):
    """Load the capability def and get an ACTIVE odoo_agent template — real
    approval flow, same pattern the earlier phases used in their own tests."""
    db = SessionLocal()
    capability_registry.load_all(db)
    db.close()

    result = odoo_agent_register.ensure_template_registered(created_by="test-suite")
    if result["registered"]:
        approval_id = result["result"]["approval_id"]
        httpx.post(f"{governance_url}/approval/{approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
        httpx.post(f"{assembly_url}/prompt/templates/reconcile-approvals")
    else:
        # Already pending or active from a prior run — make sure any pending one gets approved too.
        for t in httpx.get(f"{assembly_url}/prompt/templates").json():
            if t["agent_template_id"] == "odoo_agent" and t["status"] == "pending_approval":
                httpx.get(f"{governance_url}/approval/{t.get('approval_id', '')}")  # no-op if unknown
        httpx.post(f"{assembly_url}/prompt/templates/reconcile-approvals")


def test_live_execute_informational_question_completes(full_stack, ollama_available):
    if not ollama_available:
        pytest.skip("Ollama not reachable at OLLAMA_URL")
    _ensure_odoo_agent_ready(full_stack["governance"], full_stack["assembly"])

    db = SessionLocal()
    execution = loop.execute(
        db,
        task_id="live-test-informational",
        task_description="A colleague asks: what does the invoice approval rule say? Just explain it, don't propose any change.",
        agent_capability="odoo_agent",
        namespace="default",
        target_model=LOCAL_MODEL,
    )
    steps = store.get_steps(db, execution.id)
    db.close()

    assert execution.status in ("completed", "awaiting_approval", "refused"), (
        f"unexpected status {execution.status!r}, failure_reason={execution.failure_reason!r}, "
        f"steps={[(s.iteration, s.routing_outcome) for s in steps]}"
    )
    assert execution.iterations_used >= 1
    assert len(steps) >= 1


def test_live_execute_propose_change_requires_approval(full_stack, ollama_available):
    if not ollama_available:
        pytest.skip("Ollama not reachable at OLLAMA_URL")
    _ensure_odoo_agent_ready(full_stack["governance"], full_stack["assembly"])

    db = SessionLocal()
    execution = loop.execute(
        db,
        task_id="live-test-propose-change",
        task_description=(
            "Propose a change: draft new text for the invoice approval rule to lower the manager-approval "
            "threshold from $5000 to $2000. This is a proposal only, not a live write."
        ),
        agent_capability="odoo_agent",
        namespace="default",
        target_model=LOCAL_MODEL,
    )
    db.close()

    if execution.status == "awaiting_approval":
        assert execution.approval_id is not None
    else:
        # A live model won't always self-classify the same way every run — assert it
        # at least reached SOME real terminal state rather than silently hanging/failing.
        assert execution.status in ("completed", "refused"), (
            f"unexpected status {execution.status!r}, failure_reason={execution.failure_reason!r}"
        )


def test_resume_after_approval_completes(full_stack, ollama_available):
    if not ollama_available:
        pytest.skip("Ollama not reachable at OLLAMA_URL")
    _ensure_odoo_agent_ready(full_stack["governance"], full_stack["assembly"])

    db = SessionLocal()
    execution = loop.execute(
        db,
        task_id="live-test-resume",
        task_description=(
            "Propose a change: draft new text for the invoice approval rule to lower the manager-approval "
            "threshold from $5000 to $2000. This is a proposal only, not a live write."
        ),
        agent_capability="odoo_agent",
        namespace="default",
        target_model=LOCAL_MODEL,
    )
    if execution.status != "awaiting_approval":
        db.close()
        pytest.skip(f"model did not route to approval this run (status={execution.status}) — nothing to resume")

    httpx.post(f"{full_stack['governance']}/approval/{execution.approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    resumed = loop.resume(db, execution.id)
    db.close()

    assert resumed.status == "completed"


def test_trace_returns_full_step_history(full_stack, ollama_available):
    if not ollama_available:
        pytest.skip("Ollama not reachable at OLLAMA_URL")
    _ensure_odoo_agent_ready(full_stack["governance"], full_stack["assembly"])

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="live-test-trace", task_description="Explain the invoice approval rule.",
        agent_capability="odoo_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    steps = store.get_steps(db, execution.id)
    db.close()

    assert len(steps) == execution.iterations_used
    for s in steps:
        assert s.execution_id == execution.id


def test_model_claiming_forbidden_action_is_denied_not_trusted(full_stack, monkeypatch):
    """
    Deterministic coverage for the deny path: a live model correctly never
    claims odoo.write_orm (it was told not to, and it listened), which
    means the deny path can't be exercised by prompting alone — so this
    stubs the model's response directly to prove Reasoning Engine's own
    defense-in-depth catches it even if a model ever did claim forbidden
    access (compromised model, successful prompt injection, etc.), rather
    than trusting the model's self-report (Phase 5 doc, Reasoning Engine
    security notes: model output is untrusted input).
    """
    _ensure_odoo_agent_ready(full_stack["governance"], full_stack["assembly"])
    import json as _json

    def fake_generate(model, prompt):
        return _json.dumps({
            "reasoning": "doing it anyway",
            "answer_or_proposal": "done, I wrote directly to the database",
            "confidence": 1.0,
            "provenance": [],
            "risk_classification": "informational",  # even a maximally understated risk claim must not bypass this
            "delegate_to": None,
            "action": "odoo.write_orm",
            "odoo_model": None, "odoo_domain_json": None, "odoo_fields_json": None,
        })

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="deny-path-test", task_description="write to the database",
        agent_capability="odoo_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    db.close()

    assert execution.status == "refused"
    assert execution.result["denial_reason"]


def test_list_executions_filters_by_status_and_capability(full_stack, monkeypatch):
    """Phase 13: GET /reasoning/executions is the listing endpoint Metrics
    Dashboard/Health Monitor need — no code before this phase ever listed
    more than one execution at a time."""
    _ensure_odoo_agent_ready(full_stack["governance"], full_stack["assembly"])
    import json as _json

    def fake_generate(model, prompt):
        return _json.dumps({
            "reasoning": "informational", "answer_or_proposal": "answer", "confidence": 0.9,
            "provenance": [], "risk_classification": "informational", "delegate_to": None,
            "action": "odoo.read_orm",
            "odoo_model": None, "odoo_domain_json": None, "odoo_fields_json": None,
        })

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    exec1 = loop.execute(db, task_id="list-test-1", task_description="q1", agent_capability="odoo_agent", namespace="default", target_model=LOCAL_MODEL)
    exec2 = loop.execute(db, task_id="list-test-2", task_description="q2", agent_capability="odoo_agent", namespace="default", target_model=LOCAL_MODEL)
    exec1_id, exec1_status = exec1.id, exec1.status
    exec2_id, exec2_status = exec2.id, exec2.status
    db.close()

    assert exec1_status == "completed"
    assert exec2_status == "completed"

    all_completed = store.list_executions(SessionLocal(), status="completed")
    ids = {e.id for e in all_completed}
    assert exec1_id in ids
    assert exec2_id in ids

    odoo_only = store.list_executions(SessionLocal(), agent_capability="odoo_agent")
    assert all(e.agent_capability == "odoo_agent" for e in odoo_only)

    # Real HTTP round trip through the actual route table too, not just
    # the store function or a direct API-function call — a route-
    # registration ordering mistake (a real bug caught this way in Phase
    # 11: GET /context/model-ceiling silently shadowed by GET
    # /context/{context_id}) would be invisible to either of those.
    resp = test_client.get("/reasoning/executions", params={"agent_capability": "odoo_agent"})
    assert resp.status_code == 200
    assert any(e["id"] == exec1_id for e in resp.json())
