import json
import subprocess
import httpx
import pytest
import sqlalchemy

from agents.db import SessionLocal
from agents.reasoning_engine import loop, capability_registry
from agents.costing_agent import register as costing_agent_register
from agents.accounting_agent import register as accounting_agent_register
from agents.inventory_agent import register as inventory_agent_register

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
        "formula_name": None, "formula_ref": None, "target_namespace": None,
        "target_db": None, "sql_template": None, "params_json": None, "table": None, "impact_estimate": None,
    }
    base.update(overrides)
    return json.dumps(base)


# ---------------------------------------------------------------------------
# Capability registry
# ---------------------------------------------------------------------------

def test_all_three_new_capabilities_discovered_with_correct_boundaries():
    db = SessionLocal()
    loaded = capability_registry.load_all(db)
    for cap_name in ("costing_agent", "accounting_agent", "inventory_agent"):
        assert cap_name in loaded

    costing = capability_registry.get_capability(db, "costing_agent")
    assert costing.allowed_actions == ["costing.calculate", "costing.explain_formula", "costing.propose_formula_change"]
    assert capability_registry.local_precheck(costing, "costing.calculate") == "allow"
    assert capability_registry.local_precheck(costing, "costing.propose_formula_change") == "require_approval"
    assert capability_registry.local_precheck(costing, "costing.modify_formula_direct") == "deny"
    assert costing.classification_ceiling == "confidential"

    accounting = capability_registry.get_capability(db, "accounting_agent")
    assert capability_registry.local_precheck(accounting, "accounting.read_ledger") == "allow"
    assert capability_registry.local_precheck(accounting, "accounting.propose_entry") == "require_approval"
    assert capability_registry.local_precheck(accounting, "accounting.write_ledger_direct") == "deny"
    assert capability_registry.local_precheck(accounting, "accounting.close_period") == "deny"

    inventory = capability_registry.get_capability(db, "inventory_agent")
    assert capability_registry.local_precheck(inventory, "inventory.read_stock") == "allow"
    assert capability_registry.local_precheck(inventory, "inventory.propose_adjustment") == "require_approval"
    assert capability_registry.local_precheck(inventory, "inventory.propose_reorder") == "require_approval"
    assert capability_registry.local_precheck(inventory, "inventory.write_stock_direct") == "deny"
    db.close()


# ---------------------------------------------------------------------------
# Costing Agent — costing.propose_formula_change reaches ERP Knowledge
# Engine's real business-memory formula registration (the one genuinely
# new bridge this batch needed: erp_bridge.py).
# ---------------------------------------------------------------------------

def test_costing_propose_formula_change_reaches_real_erp_knowledge_engine(full_stack, knowledge_pipelines_url, monkeypatch):
    _ensure_ready(costing_agent_register, full_stack["governance"], full_stack["assembly"])

    def fake_generate(model, prompt):
        return _stub(
            "costing.propose_formula_change", answer_or_proposal="Add a 5% rush-order surcharge to standard machining cost.",
            formula_name="rush_order_surcharge", formula_ref="base_cost * 1.05", target_namespace="proj-costing-test-1",
            risk_classification="high",
        )

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="costing-formula-test-1", task_description="Add a rush-order surcharge formula.",
        agent_capability="costing_agent", namespace="proj-costing-test-1", target_model=LOCAL_MODEL,
    )
    assert execution.status == "awaiting_approval"

    httpx.post(f"{full_stack['governance']}/approval/{execution.approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    resumed = loop.resume(db, execution.id)
    db.close()

    assert resumed.status == "completed"
    erp_execution = resumed.result["erp_execution"]
    assert erp_execution["attempted"] is True
    formula_result = erp_execution["result"]
    assert formula_result["ok"] is True
    assert formula_result["name"] == "rush_order_surcharge"
    assert formula_result["classification"] in ("internal", "confidential")

    # Independently verify the real formula record via ERP Knowledge Engine's own endpoint.
    fetched = httpx.get(f"{knowledge_pipelines_url}/erp-knowledge/formula/{formula_result['id']}").json()
    assert fetched["formula_ref"] == "base_cost * 1.05"
    assert fetched["business_purpose"] == "Add a 5% rush-order surcharge to standard machining cost."


def test_costing_calculate_is_informational_and_needs_no_approval(full_stack, monkeypatch):
    _ensure_ready(costing_agent_register, full_stack["governance"], full_stack["assembly"])

    def fake_generate(model, prompt):
        return _stub("costing.calculate", answer_or_proposal="Applying the standard formula: $420.00.", risk_classification="informational")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="costing-calc-test-1", task_description="What's the cost of 10 units at standard rate?",
        agent_capability="costing_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    db.close()
    assert execution.status == "completed"


# ---------------------------------------------------------------------------
# Accounting Agent — accounting.read_ledger reuses database_bridge's db.read
# tool call unchanged; accounting.propose_entry ALWAYS requires approval
# and materializes as a real git-committed document (execution_bridge),
# never a direct write — the doc's deliberately conservative design.
# ---------------------------------------------------------------------------

def test_accounting_read_ledger_tool_call_returns_real_data(full_stack, database_url, monkeypatch):
    _ensure_ready(accounting_agent_register, full_stack["governance"], full_stack["assembly"])
    calls = {"count": 0}

    def fake_generate(model, prompt):
        calls["count"] += 1
        if calls["count"] == 1:
            assert "SO0001" not in prompt
            return _stub(
                "db.read", target_db="demo_erp", table="sale_order",
                sql_template="SELECT name, amount_total FROM sale_order WHERE id = :id",
                params_json=json.dumps({"id": 1}),
            )
        assert "SO0001" in prompt
        return _stub("accounting.read_ledger", sql_template="", answer_or_proposal="Order SO0001 totals 1250.00.", risk_classification="informational")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="accounting-read-test-1", task_description="What's the total for sale order 1?",
        agent_capability="accounting_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    db.close()

    assert execution.status == "completed"
    assert execution.iterations_used == 2


def test_accounting_propose_entry_always_requires_approval_even_at_low_risk(full_stack, monkeypatch):
    """The doc's explicit rule: no impact-size exception, ever — confirmed
    here even when the model itself self-assesses low risk."""
    _ensure_ready(accounting_agent_register, full_stack["governance"], full_stack["assembly"])

    def fake_generate(model, prompt):
        return _stub("accounting.propose_entry", answer_or_proposal="Book a $12 office-supplies expense to account 6100.", risk_classification="low")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="accounting-propose-test-1", task_description="Book a small office supplies expense.",
        agent_capability="accounting_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    db.close()
    assert execution.status == "awaiting_approval"


def test_accounting_propose_entry_materializes_as_a_real_git_document_not_a_write(
    full_stack, execution_url, proposal_repo, disposable_bare_repo_for_bridge, monkeypatch,
):
    _ensure_ready(accounting_agent_register, full_stack["governance"], full_stack["assembly"])
    proposal_text = "Book a $4,200 equipment depreciation entry for Q3."

    def fake_generate(model, prompt):
        return _stub("accounting.propose_entry", answer_or_proposal=proposal_text, risk_classification="medium")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="accounting-propose-test-2", task_description="Book a depreciation entry.",
        agent_capability="accounting_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    assert execution.status == "awaiting_approval"

    httpx.post(f"{full_stack['governance']}/approval/{execution.approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    resumed = loop.resume(db, execution.id)
    db.close()

    assert resumed.status == "completed"
    git_execution = resumed.result["git_execution"]
    assert git_execution["attempted"] is True
    branch_name = git_execution["branch_name"]
    assert branch_name == "accounting-agent/task-accounting-propose-test-2"

    show_output = subprocess.run(
        ["git", "show", f"{branch_name}:proposals/accounting-propose-test-2.md"],
        cwd=str(disposable_bare_repo_for_bridge), capture_output=True, text=True,
    ).stdout
    assert proposal_text in show_output


# ---------------------------------------------------------------------------
# Inventory Agent — reuses database_agent's exact dry-run-then-write path
# (database_bridge.materialize_propose_write) for a second agent, with
# zero changes to that bridge.
# ---------------------------------------------------------------------------

def test_inventory_read_stock_tool_call_returns_real_data(full_stack, database_url, monkeypatch):
    _ensure_ready(inventory_agent_register, full_stack["governance"], full_stack["assembly"])
    calls = {"count": 0}

    def fake_generate(model, prompt):
        calls["count"] += 1
        if calls["count"] == 1:
            return _stub(
                "db.read", target_db="demo_erp", table="sale_order",
                sql_template="SELECT name, state FROM sale_order WHERE id = :id",
                params_json=json.dumps({"id": 1}),
            )
        assert "SO0001" in prompt
        return _stub("inventory.read_stock", sql_template="", answer_or_proposal="SO0001 is in sale state.", risk_classification="informational")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="inventory-read-test-1", task_description="What's the status of order 1?",
        agent_capability="inventory_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    db.close()

    assert execution.status == "completed"
    assert execution.iterations_used == 2


def test_inventory_dry_run_then_propose_adjustment_then_approve_executes_real_write(
    full_stack, database_url, demo_erp_clean, monkeypatch,
):
    """
    Same real disposable target and dry-run-before-write discipline
    Phase 7's Database Agent already proved (demo_erp has no literal
    stock table in this environment — see services/agents/README.md's
    honesty notes — so this proves the WIRING: inventory_agent's own
    policy role and capability boundary driving the exact same
    database_bridge.materialize_propose_write path, unchanged).
    """
    _ensure_ready(inventory_agent_register, full_stack["governance"], full_stack["assembly"])
    sql_template = "UPDATE sale_order SET state = :state WHERE name = :name"
    params_json = json.dumps({"state": "cancel", "name": "SO0003"})
    calls = {"count": 0}

    def fake_generate(model, prompt):
        calls["count"] += 1
        if calls["count"] == 1:
            return _stub("db.dry_run", target_db="demo_erp", sql_template=sql_template, params_json=params_json)
        assert "row(s) affected" in prompt
        return _stub(
            "inventory.propose_adjustment", target_db="demo_erp", sql_template=sql_template, params_json=params_json,
            impact_estimate="1 row affected per the dry-run", risk_classification="medium",
        )

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="inventory-adjust-test-1", task_description="Cancel sale order SO0003 due to stock shortage.",
        agent_capability="inventory_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    assert execution.status == "awaiting_approval"
    assert execution.result["dry_run_id"]

    httpx.post(f"{full_stack['governance']}/approval/{execution.approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    resumed = loop.resume(db, execution.id)
    db.close()

    assert resumed.status == "completed"
    db_execution = resumed.result["db_execution"]
    assert db_execution["attempted"] is True
    assert db_execution["result"]["ok"] is True

    target_engine = sqlalchemy.create_engine("postgresql://saadi:devpassword@localhost:5432/demo_erp")
    with target_engine.connect() as conn:
        state = conn.execute(sqlalchemy.text("SELECT state FROM sale_order WHERE name = 'SO0003'")).scalar()
    assert state == "cancel"


# ---------------------------------------------------------------------------
# Live-model smoke tests
# ---------------------------------------------------------------------------

_TERMINAL_STATES = ("completed", "awaiting_approval", "refused", "delegated", "awaiting_delegation", "failed")


@pytest.mark.parametrize("agent_capability,register_module,question", [
    ("costing_agent", costing_agent_register, "Explain, in one sentence, what a costing formula does. Don't propose any changes."),
    ("accounting_agent", accounting_agent_register, "Explain, in one sentence, what a ledger entry is. Don't propose any changes or read anything."),
    ("inventory_agent", inventory_agent_register, "Explain, in one sentence, what stock reordering means. Don't propose any changes or read anything."),
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
