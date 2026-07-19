import json
import subprocess
import httpx
import pytest

from agents.db import SessionLocal
from agents.reasoning_engine import loop, capability_registry
from agents.odoo_agent import register as odoo_agent_register

LOCAL_MODEL = "qwen3.5:4b"


def _ensure_odoo_agent_ready(governance_url, assembly_url):
    db = SessionLocal()
    capability_registry.load_all(db)
    db.close()

    result = odoo_agent_register.ensure_template_registered(created_by="test-suite")
    if result["registered"]:
        approval_id = result["result"]["approval_id"]
        httpx.post(f"{governance_url}/approval/{approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
        httpx.post(f"{assembly_url}/prompt/templates/reconcile-approvals")
    else:
        httpx.post(f"{assembly_url}/prompt/templates/reconcile-approvals")


def test_approved_propose_change_materializes_as_real_branch_commit_push(
    full_stack, execution_url, proposal_repo, disposable_bare_repo_for_bridge, monkeypatch,
):
    """
    The Phase 6 doc's Section 3 diagram, exercised through the actual
    Phase 5 loop, not just the execution service in isolation: a model
    response is stubbed deterministically here (the routing decision
    itself — risk_classification above informational routes to approval —
    is already verified against a real live model in
    test_reasoning_engine.py; what's new here is proving the approved
    result actually gets materialized as a real branch/commit/push
    against a real disposable repo, which needs a reliable trigger, not
    one more roll of the dice on model phrasing).
    """
    _ensure_odoo_agent_ready(full_stack["governance"], full_stack["assembly"])

    proposal_text = "Lower the invoice manager-approval threshold from $5000 to $2000."

    def fake_generate(model, prompt):
        return json.dumps({
            "reasoning": "Drafting the requested threshold change as a proposal for human review.",
            "answer_or_proposal": proposal_text,
            "confidence": 0.9,
            "provenance": [],
            "risk_classification": "medium",
            "delegate_to": None,
            "action": "odoo.propose_change",
        })

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="bridge-test-1", task_description="Propose lowering the invoice approval threshold.",
        agent_capability="odoo_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    assert execution.status == "awaiting_approval"

    httpx.post(f"{full_stack['governance']}/approval/{execution.approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    resumed = loop.resume(db, execution.id)
    db.close()

    assert resumed.status == "completed"
    git_execution = resumed.result["git_execution"]
    assert git_execution["attempted"] is True
    assert git_execution["stage"] == "open_mr"  # made it all the way through branch/commit/push
    assert git_execution["commit_sha"]

    # Independent verification against the real disposable remote, not
    # the execution service's own report of success.
    branch_name = git_execution["branch_name"]
    assert branch_name == f"odoo-agent/task-bridge-test-1"
    remote_log = subprocess.run(
        ["git", "log", "-1", "--format=%B", branch_name],
        cwd=str(disposable_bare_repo_for_bridge), capture_output=True, text=True,
    ).stdout
    assert "Propose change for task bridge-test-1" in remote_log
    assert "Task-Id: bridge-test-1" in remote_log
    assert "Agent-Capability: odoo_agent" in remote_log
    assert f"Reasoning-Execution-Id: {execution.id}" in remote_log

    # The actual proposal text landed in the committed file, not just the DB.
    show_output = subprocess.run(
        ["git", "show", f"{branch_name}:proposals/bridge-test-1.md"],
        cwd=str(disposable_bare_repo_for_bridge), capture_output=True, text=True,
    ).stdout
    assert proposal_text in show_output

    # And the MR step ran and reported honestly rather than a fake success.
    assert git_execution["mr_result"]["status"] == "not_configured"
