import json
import subprocess
import httpx
import pytest

from agents.db import SessionLocal
from agents.reasoning_engine import loop, capability_registry
from agents.manufacturing_agent import register as manufacturing_agent_register
from agents.sales_agent import register as sales_agent_register
from agents.project_management_agent import register as project_management_agent_register

LOCAL_MODEL = "qwen3.5:4b"


def _ensure_ready(register_module, governance_url, assembly_url):
    db = SessionLocal()
    capability_registry.load_all(db)
    db.close()

    result = register_module.ensure_template_registered(created_by="test-suite")
    if result["registered"]:
        approval_id = result["result"]["approval_id"]
        httpx.post(f"{governance_url}/approval/{approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    httpx.post(f"{assembly_url}/prompt/templates/reconcile-approvals")


def _stub(action, **overrides):
    base = {
        "reasoning": "test reasoning", "answer_or_proposal": "test answer", "confidence": 0.9,
        "provenance": [], "risk_classification": "medium", "delegate_to": None, "action": action,
        "target_db": None, "sql_template": None, "params_json": None, "table": None,
        "pii_fields_requested_json": None, "target_task_id": None,
    }
    base.update(overrides)
    return json.dumps(base)


# ---------------------------------------------------------------------------
# Capability registry
# ---------------------------------------------------------------------------

def test_all_three_new_capabilities_discovered_with_correct_boundaries():
    db = SessionLocal()
    loaded = capability_registry.load_all(db)
    for cap_name in ("manufacturing_agent", "sales_agent", "project_management_agent"):
        assert cap_name in loaded

    manufacturing = capability_registry.get_capability(db, "manufacturing_agent")
    assert capability_registry.local_precheck(manufacturing, "manufacturing.explain_workflow") == "allow"
    assert capability_registry.local_precheck(manufacturing, "manufacturing.flag_constraint") == "allow"
    assert capability_registry.local_precheck(manufacturing, "manufacturing.propose_schedule_change") == "require_approval"
    assert capability_registry.local_precheck(manufacturing, "manufacturing.execute_schedule_direct") == "deny"

    sales = capability_registry.get_capability(db, "sales_agent")
    assert capability_registry.local_precheck(sales, "sales.explain_status") == "allow"
    assert capability_registry.local_precheck(sales, "sales.propose_quote") == "require_approval"
    assert capability_registry.local_precheck(sales, "sales.propose_order_change") == "require_approval"
    assert capability_registry.local_precheck(sales, "sales.execute_order_direct") == "deny"
    assert capability_registry.local_precheck(sales, "sales.access_full_customer_pii_unscoped") == "deny"

    pm = capability_registry.get_capability(db, "project_management_agent")
    assert capability_registry.local_precheck(pm, "pm.explain_status") == "allow"
    assert capability_registry.local_precheck(pm, "pm.flag_at_risk") == "allow"
    assert capability_registry.local_precheck(pm, "pm.propose_milestone_update") == "require_approval"
    assert capability_registry.local_precheck(pm, "pm.close_project_direct") == "deny"
    db.close()


# ---------------------------------------------------------------------------
# Manufacturing Agent — manufacturing.flag_constraint reuses database_bridge's
# db.read tool call unchanged; manufacturing.propose_schedule_change
# materializes via execution_bridge, same as every other propose_* action.
# ---------------------------------------------------------------------------

def test_manufacturing_flag_constraint_tool_call_returns_real_data(full_stack, database_url, monkeypatch):
    _ensure_ready(manufacturing_agent_register, full_stack["governance"], full_stack["assembly"])
    calls = {"count": 0}

    def fake_generate(model, prompt):
        calls["count"] += 1
        if calls["count"] == 1:
            return _stub(
                "db.read", target_db="demo_erp", table="sale_order",
                sql_template="SELECT name, amount_total FROM sale_order WHERE id = :id",
                params_json=json.dumps({"id": 1}),
            )
        assert "SO0001" in prompt
        return _stub("manufacturing.flag_constraint", sql_template="", answer_or_proposal="No capacity constraint found for SO0001.", risk_classification="informational")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="manufacturing-flag-test-1", task_description="Check for capacity constraints on order 1.",
        agent_capability="manufacturing_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    db.close()

    assert execution.status == "completed"
    assert execution.iterations_used == 2


def test_manufacturing_propose_schedule_change_materializes_as_a_real_git_document(
    full_stack, execution_url, proposal_repo, disposable_bare_repo_for_bridge, monkeypatch,
):
    _ensure_ready(manufacturing_agent_register, full_stack["governance"], full_stack["assembly"])
    proposal_text = "Push the SO0002 production run back two days to free capacity for a rush order."

    def fake_generate(model, prompt):
        return _stub("manufacturing.propose_schedule_change", answer_or_proposal=proposal_text, risk_classification="medium")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="manufacturing-propose-test-1", task_description="Push back a production run.",
        agent_capability="manufacturing_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    assert execution.status == "awaiting_approval"

    httpx.post(f"{full_stack['governance']}/approval/{execution.approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    resumed = loop.resume(db, execution.id)
    db.close()

    assert resumed.status == "completed"
    git_execution = resumed.result["git_execution"]
    assert git_execution["attempted"] is True
    branch_name = git_execution["branch_name"]
    assert branch_name == "manufacturing-agent/task-manufacturing-propose-test-1"

    show_output = subprocess.run(
        ["git", "show", f"{branch_name}:proposals/manufacturing-propose-test-1.md"],
        cwd=str(disposable_bare_repo_for_bridge), capture_output=True, text=True,
    ).stdout
    assert proposal_text in show_output


# ---------------------------------------------------------------------------
# Sales Agent — the first agent to use the PII dimension end to end
# (Phase 15's one genuinely new Database Connector extension).
# ---------------------------------------------------------------------------

def test_sales_explain_status_without_pii_request_never_sees_email(full_stack, database_url, monkeypatch):
    """Minimum-necessary by default: not naming a PII field means never
    getting it back, even though sales_agent IS authorized in principle."""
    _ensure_ready(sales_agent_register, full_stack["governance"], full_stack["assembly"])
    calls = {"count": 0}

    def fake_generate(model, prompt):
        calls["count"] += 1
        if calls["count"] == 1:
            return _stub(
                "db.read", target_db="demo_erp", table="res_partner",
                sql_template="SELECT id, name FROM res_partner WHERE id = :id",
                params_json=json.dumps({"id": 1}), pii_fields_requested_json="[]",
            )
        assert "ops@acme.example" not in prompt
        return _stub("sales.explain_status", sql_template="", answer_or_proposal="Customer is Acme Manufacturing.", risk_classification="informational")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="sales-status-test-1", task_description="Who is the customer for order 1?",
        agent_capability="sales_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    db.close()
    assert execution.status == "completed"


def test_sales_explain_status_with_explicit_pii_request_gets_real_email(full_stack, database_url, monkeypatch):
    """The only way sales_agent ever sees a real PII value: name it
    explicitly, per task, via pii_fields_requested_json."""
    _ensure_ready(sales_agent_register, full_stack["governance"], full_stack["assembly"])
    calls = {"count": 0}

    def fake_generate(model, prompt):
        calls["count"] += 1
        if calls["count"] == 1:
            return _stub(
                "db.read", target_db="demo_erp", table="res_partner",
                sql_template="SELECT id, name, email FROM res_partner WHERE id = :id",
                params_json=json.dumps({"id": 1}), pii_fields_requested_json=json.dumps(["email"]),
            )
        assert "ops@acme.example" in prompt
        return _stub("sales.explain_status", sql_template="", answer_or_proposal="Confirmed contact: ops@acme.example.", risk_classification="informational")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="sales-status-test-2", task_description="Confirm the contact email for order 1's customer before I send a quote.",
        agent_capability="sales_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    db.close()
    assert execution.status == "completed"
    assert execution.iterations_used == 2


def test_sales_propose_quote_materializes_as_a_real_git_document(
    full_stack, execution_url, proposal_repo, disposable_bare_repo_for_bridge, monkeypatch,
):
    _ensure_ready(sales_agent_register, full_stack["governance"], full_stack["assembly"])
    proposal_text = "Quote 50 units of custom bracket at $18.40/unit, based on Costing Agent's standard formula."

    def fake_generate(model, prompt):
        return _stub("sales.propose_quote", answer_or_proposal=proposal_text, risk_classification="medium")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="sales-quote-test-1", task_description="Draft a quote for 50 custom brackets.",
        agent_capability="sales_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    assert execution.status == "awaiting_approval"

    httpx.post(f"{full_stack['governance']}/approval/{execution.approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    resumed = loop.resume(db, execution.id)
    db.close()

    assert resumed.status == "completed"
    git_execution = resumed.result["git_execution"]
    assert git_execution["attempted"] is True
    branch_name = git_execution["branch_name"]
    assert branch_name == "sales-agent/task-sales-quote-test-1"

    show_output = subprocess.run(
        ["git", "show", f"{branch_name}:proposals/sales-quote-test-1.md"],
        cwd=str(disposable_bare_repo_for_bridge), capture_output=True, text=True,
    ).stdout
    assert proposal_text in show_output


# ---------------------------------------------------------------------------
# Project Management Agent — the one genuinely new tool-call mechanism
# this batch needed (task_bridge.py / GET /tasks/{id}/events), reasoning
# over Task Manager's own real task history rather than ERP data.
# ---------------------------------------------------------------------------

def test_pm_task_read_tool_call_returns_real_task_history(full_stack, monkeypatch):
    _ensure_ready(project_management_agent_register, full_stack["governance"], full_stack["assembly"])

    created = httpx.post(
        f"{full_stack['platform']}/api/v1/tasks",
        json={"title": "a real task to look up"},
        headers={"Authorization": "Bearer dev-odoo-agent-token"},
    ).json()
    target_task_id = created["id"]
    httpx.post(
        f"{full_stack['platform']}/api/v1/tasks/{target_task_id}/status",
        json={"status": "in_progress", "detail": "picked up by a worker"},
        headers={"Authorization": "Bearer dev-odoo-agent-token"},
    )

    calls = {"count": 0}

    def fake_generate(model, prompt):
        calls["count"] += 1
        if calls["count"] == 1:
            return _stub("task.read", target_task_id=target_task_id)
        assert "in_progress" in prompt
        assert "picked up by a worker" in prompt
        return _stub("pm.explain_status", target_task_id="", answer_or_proposal=f"Task {target_task_id} is in_progress; it was picked up by a worker.", risk_classification="informational")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="pm-taskread-test-1", task_description=f"Why is task {target_task_id} taking a while?",
        agent_capability="project_management_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    db.close()

    assert execution.status == "completed"
    assert execution.iterations_used == 2


def test_pm_propose_milestone_update_materializes_as_a_real_git_document(
    full_stack, execution_url, proposal_repo, disposable_bare_repo_for_bridge, monkeypatch,
):
    _ensure_ready(project_management_agent_register, full_stack["governance"], full_stack["assembly"])
    proposal_text = "Move the 'frame assembly complete' milestone out by one week; supplier delay on raw stock."

    def fake_generate(model, prompt):
        return _stub("pm.propose_milestone_update", answer_or_proposal=proposal_text, risk_classification="medium")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="pm-milestone-test-1", task_description="Update the frame assembly milestone.",
        agent_capability="project_management_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    assert execution.status == "awaiting_approval"

    httpx.post(f"{full_stack['governance']}/approval/{execution.approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    resumed = loop.resume(db, execution.id)
    db.close()

    assert resumed.status == "completed"
    git_execution = resumed.result["git_execution"]
    assert git_execution["attempted"] is True
    branch_name = git_execution["branch_name"]
    assert branch_name == "project-management-agent/task-pm-milestone-test-1"

    show_output = subprocess.run(
        ["git", "show", f"{branch_name}:proposals/pm-milestone-test-1.md"],
        cwd=str(disposable_bare_repo_for_bridge), capture_output=True, text=True,
    ).stdout
    assert proposal_text in show_output


# ---------------------------------------------------------------------------
# Live-model smoke tests
# ---------------------------------------------------------------------------

_TERMINAL_STATES = ("completed", "awaiting_approval", "refused", "delegated", "awaiting_delegation", "failed")


@pytest.mark.parametrize("agent_capability,register_module,question", [
    ("manufacturing_agent", manufacturing_agent_register, "Explain, in one sentence, what a production workflow is. Don't propose any changes or read anything."),
    ("sales_agent", sales_agent_register, "Explain, in one sentence, what a sales quote is. Don't propose any changes, read anything, or request any PII fields."),
    ("project_management_agent", project_management_agent_register, "Explain, in one sentence, what a project milestone is. Don't propose any changes or look up any task."),
])
def test_live_explain_only_smoke(full_stack, ollama_available, agent_capability, register_module, question):
    if not ollama_available:
        pytest.skip("Ollama not reachable at OLLAMA_URL")
    _ensure_ready(register_module, full_stack["governance"], full_stack["assembly"])

    db = SessionLocal()
    execution = loop.execute(
        db, task_id=f"{agent_capability}-live-test-1", task_description=question,
        agent_capability=agent_capability, namespace="default", target_model=LOCAL_MODEL, max_iterations=6,
    )
    db.close()
    assert execution.status in _TERMINAL_STATES, f"unexpected status {execution.status!r}, failure_reason={execution.failure_reason!r}"
    assert execution.iterations_used >= 1
