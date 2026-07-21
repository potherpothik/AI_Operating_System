import json
import subprocess
import uuid
import httpx
import pytest

from agents.db import SessionLocal
from agents.reasoning_engine import loop, capability_registry
from agents.python_agent import register as python_agent_register
from agents.documentation_agent import register as documentation_agent_register
from agents.security_agent import register as security_agent_register
from agents.research_agent import register as research_agent_register

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
        "audit_correlation_id": None, "audit_actor_id": None, "audit_action": None,
        "mcp_server_name": None, "mcp_tool_name": None, "mcp_params_json": None,
    }
    base.update(overrides)
    return json.dumps(base)


# ---------------------------------------------------------------------------
# Capability registry
# ---------------------------------------------------------------------------

def test_all_four_new_capabilities_discovered_with_correct_boundaries():
    db = SessionLocal()
    loaded = capability_registry.load_all(db)
    for cap_name in ("python_agent", "documentation_agent", "security_agent", "research_agent"):
        assert cap_name in loaded

    python_ = capability_registry.get_capability(db, "python_agent")
    assert capability_registry.local_precheck(python_, "python.explain_code") == "allow"
    assert capability_registry.local_precheck(python_, "python.propose_script") == "allow"
    assert capability_registry.local_precheck(python_, "python.propose_change") == "require_approval"
    assert capability_registry.local_precheck(python_, "python.execute_direct") == "deny"

    documentation = capability_registry.get_capability(db, "documentation_agent")
    assert capability_registry.local_precheck(documentation, "docs.answer_from_existing") == "allow"
    assert capability_registry.local_precheck(documentation, "docs.propose_new_doc") == "require_approval"
    assert capability_registry.local_precheck(documentation, "docs.publish_direct") == "deny"

    security = capability_registry.get_capability(db, "security_agent")
    assert capability_registry.local_precheck(security, "security.review_change") == "allow"
    assert capability_registry.local_precheck(security, "security.explain_risk") == "allow"
    assert capability_registry.local_precheck(security, "security.audit_query") == "allow"
    assert capability_registry.local_precheck(security, "security.modify_policy_direct") == "deny"
    assert capability_registry.local_precheck(security, "security.grant_permission") == "deny"

    research = capability_registry.get_capability(db, "research_agent")
    assert capability_registry.local_precheck(research, "research.synthesize_internal") == "allow"
    assert capability_registry.local_precheck(research, "research.propose_external_lookup") == "require_approval"
    assert capability_registry.local_precheck(research, "research.access_external_direct") == "deny"
    db.close()


# ---------------------------------------------------------------------------
# Python Agent — needs zero new mechanism, reuses execution_bridge unchanged.
# ---------------------------------------------------------------------------

def test_python_propose_change_materializes_as_a_real_git_document(
    full_stack, execution_url, proposal_repo, disposable_bare_repo_for_bridge, monkeypatch,
):
    _ensure_ready(python_agent_register, full_stack["governance"], full_stack["assembly"])
    proposal_text = "Extract the repeated retry logic into a shared decorator."

    def fake_generate(model, prompt):
        return _stub("python.propose_change", answer_or_proposal=proposal_text, risk_classification="medium")

    monkeypatch.setattr(loop, "generate", fake_generate)

    task_id = f"python-propose-test-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    execution = loop.execute(
        db, task_id=task_id, task_description="Propose extracting retry logic into a decorator.",
        agent_capability="python_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    assert execution.status == "awaiting_approval"

    httpx.post(f"{full_stack['governance']}/approval/{execution.approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    resumed = loop.resume(db, execution.id)
    db.close()

    assert resumed.status == "completed"
    git_execution = resumed.result["git_execution"]
    assert git_execution["attempted"] is True
    branch_name = git_execution["branch_name"]
    assert branch_name == f"python-agent/task-{task_id}"

    show_output = subprocess.run(
        ["git", "show", f"{branch_name}:proposals/{task_id}.md"],
        cwd=str(disposable_bare_repo_for_bridge), capture_output=True, text=True,
    ).stdout
    assert proposal_text in show_output


# ---------------------------------------------------------------------------
# Documentation Agent — the one real extension this batch needed: reusing
# Phase 16's reverse_eng_bridge chained docs-ingest step for a SECOND agent.
# ---------------------------------------------------------------------------

def test_docs_propose_new_doc_materializes_and_ingests_for_real(
    full_stack, execution_url, knowledge_pipelines_url, proposal_repo, disposable_bare_repo_for_bridge, monkeypatch,
):
    _ensure_ready(documentation_agent_register, full_stack["governance"], full_stack["assembly"])
    draft_text = "How to add a new agent capability: create capability.yaml + template.md, wire governance, add tests."

    def fake_generate(model, prompt):
        return _stub("docs.propose_new_doc", answer_or_proposal=draft_text, risk_classification="medium")

    monkeypatch.setattr(loop, "generate", fake_generate)

    task_id = f"docs-propose-test-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    execution = loop.execute(
        db, task_id=task_id, task_description="Draft a new-agent-capability how-to doc.",
        agent_capability="documentation_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    assert execution.status == "awaiting_approval"

    httpx.post(f"{full_stack['governance']}/approval/{execution.approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    resumed = loop.resume(db, execution.id)
    db.close()

    assert resumed.status == "completed"
    git_execution = resumed.result["git_execution"]
    assert git_execution["attempted"] is True
    branch_name = git_execution["branch_name"]
    assert branch_name == f"documentation-agent/task-{task_id}"

    show_output = subprocess.run(
        ["git", "show", f"{branch_name}:proposals/{task_id}.md"],
        cwd=str(disposable_bare_repo_for_bridge), capture_output=True, text=True,
    ).stdout
    assert draft_text in show_output

    # The one genuinely new thing this agent needed: reverse_eng_bridge's
    # chained ingest step, reused completely unchanged for a second agent.
    docs_execution = resumed.result["docs_execution"]
    assert docs_execution["attempted"] is True
    assert docs_execution["result"]["ok"] is True
    document_id = docs_execution["result"]["document_id"]

    sources = httpx.get(f"{knowledge_pipelines_url}/docs/sources", params={"project_id": task_id}).json()["sources"]
    assert any(s["document_id"] == document_id for s in sources)


# ---------------------------------------------------------------------------
# Security Agent — the one genuinely new tool call this phase needed: a
# real audit trail lookup, plus the correlation_id gap-fill it surfaced.
# ---------------------------------------------------------------------------

def test_security_audit_query_tool_call_returns_a_real_audit_trail(full_stack, monkeypatch):
    _ensure_ready(security_agent_register, full_stack["governance"], full_stack["assembly"])

    # Real audit events with a known correlation_id, written the same way
    # any other service already does via the shared /audit/log endpoint.
    corr_id = f"security-audit-test-{uuid.uuid4().hex[:8]}"
    httpx.post(
        f"{full_stack['governance']}/audit/log",
        json={"actor_id": "manufacturing_agent", "actor_type": "agent", "action": "manufacturing.propose_schedule_change", "resource": "task-x", "correlation_id": corr_id},
    )
    httpx.post(
        f"{full_stack['governance']}/audit/log",
        json={"actor_id": "manufacturing_agent", "actor_type": "agent", "action": "reasoning.require_approval", "resource": "task-x", "correlation_id": corr_id},
    )

    calls = {"count": 0}

    def fake_generate(model, prompt):
        calls["count"] += 1
        if calls["count"] == 1:
            return _stub("security.audit_query", audit_correlation_id=corr_id)
        assert "manufacturing.propose_schedule_change" in prompt
        assert "reasoning.require_approval" in prompt
        return _stub("security.explain_risk", audit_correlation_id="", answer_or_proposal="Two real events found for this task.", risk_classification="informational")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id=f"security-test-{uuid.uuid4().hex[:8]}", task_description=f"What happened for correlation {corr_id}?",
        agent_capability="security_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    db.close()

    assert execution.status == "completed"
    assert execution.iterations_used == 2


# ---------------------------------------------------------------------------
# Research Agent — needs zero new mechanism; approval is unconditional.
# ---------------------------------------------------------------------------

def test_research_propose_external_lookup_materializes_as_a_real_git_document(
    full_stack, execution_url, proposal_repo, disposable_bare_repo_for_bridge, monkeypatch,
):
    _ensure_ready(research_agent_register, full_stack["governance"], full_stack["assembly"])
    proposal_text = "Look up the current published spec for DXF R2018 dimension entity fields."

    def fake_generate(model, prompt):
        return _stub("research.propose_external_lookup", answer_or_proposal=proposal_text, risk_classification="low")

    monkeypatch.setattr(loop, "generate", fake_generate)

    task_id = f"research-propose-test-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    execution = loop.execute(
        db, task_id=task_id, task_description="Propose an external lookup for DXF spec details.",
        agent_capability="research_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    # Unconditional approval requirement — fires even at risk_classification="low".
    assert execution.status == "awaiting_approval"

    httpx.post(f"{full_stack['governance']}/approval/{execution.approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    resumed = loop.resume(db, execution.id)
    db.close()

    assert resumed.status == "completed"
    git_execution = resumed.result["git_execution"]
    assert git_execution["attempted"] is True
    branch_name = git_execution["branch_name"]
    assert branch_name == f"research-agent/task-{task_id}"

    show_output = subprocess.run(
        ["git", "show", f"{branch_name}:proposals/{task_id}.md"],
        cwd=str(disposable_bare_repo_for_bridge), capture_output=True, text=True,
    ).stdout
    assert proposal_text in show_output


# ---------------------------------------------------------------------------
# Live-model smoke tests
# ---------------------------------------------------------------------------

_TERMINAL_STATES = ("completed", "awaiting_approval", "refused", "delegated", "awaiting_delegation", "failed")


@pytest.mark.parametrize("agent_capability,register_module,question", [
    ("python_agent", python_agent_register, "In one sentence, explain what a Python decorator is. This is a general Python question, not Odoo- or Django-specific, so don't delegate. Don't propose any change."),
    ("documentation_agent", documentation_agent_register, "In one sentence, explain what documentation-as-code means. Don't propose any new doc."),
    ("security_agent", security_agent_register, "In one sentence, explain why an advisory recommendation is not the same as Security Layer enforcement. Don't query any audit trail."),
    ("research_agent", research_agent_register, "In one sentence, explain why this system defaults to internal-knowledge-only. Don't propose any external lookup."),
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
