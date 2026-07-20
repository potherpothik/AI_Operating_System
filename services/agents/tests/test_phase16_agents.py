import json
import subprocess
import uuid
import httpx
import pytest

from agents.db import SessionLocal
from agents.reasoning_engine import loop, capability_registry
from agents.code_review_agent import register as code_review_agent_register
from agents.reverse_engineering_agent import register as reverse_engineering_agent_register
from agents.architecture_agent import register as architecture_agent_register

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
        "target_repo": None, "target_branch": None, "symbol_ref": None, "target_approval_id": None,
    }
    base.update(overrides)
    return json.dumps(base)


# ---------------------------------------------------------------------------
# Capability registry
# ---------------------------------------------------------------------------

def test_all_three_new_capabilities_discovered_with_correct_boundaries():
    db = SessionLocal()
    loaded = capability_registry.load_all(db)
    for cap_name in ("code_review_agent", "reverse_engineering_agent", "architecture_agent"):
        assert cap_name in loaded

    review = capability_registry.get_capability(db, "code_review_agent")
    assert capability_registry.local_precheck(review, "review.fetch_diff") == "allow"
    assert capability_registry.local_precheck(review, "review.check_callers") == "allow"
    assert capability_registry.local_precheck(review, "review.flag_concern") == "allow"
    assert capability_registry.local_precheck(review, "review.approve_recommendation") == "allow"
    assert capability_registry.local_precheck(review, "review.merge") == "deny"
    assert capability_registry.local_precheck(review, "review.override_human_approval") == "deny"

    reverse_eng = capability_registry.get_capability(db, "reverse_engineering_agent")
    assert capability_registry.local_precheck(reverse_eng, "reverse_eng.explain_undocumented") == "allow"
    assert capability_registry.local_precheck(reverse_eng, "reverse_eng.propose_documentation_draft") == "require_approval"
    assert capability_registry.local_precheck(reverse_eng, "reverse_eng.modify_code_direct") == "deny"

    architecture = capability_registry.get_capability(db, "architecture_agent")
    assert capability_registry.local_precheck(architecture, "architecture.explain_existing") == "allow"
    assert capability_registry.local_precheck(architecture, "architecture.propose_decision") == "require_approval"
    assert capability_registry.local_precheck(architecture, "architecture.implement_direct") == "deny"
    db.close()


# ---------------------------------------------------------------------------
# Code Review Agent — the two real tool calls (real diff, real call-graph
# lookup) plus the new attach_review mechanism landing on ANOTHER agent's
# real pending approval.
# ---------------------------------------------------------------------------

@pytest.fixture
def code_analysis_repo(tmp_path, knowledge_pipelines_url):
    """A real repo with a real, resolvable intra-file call edge
    (Widget.render -> helper), scanned for real via the live Code
    Analysis Engine — same fixture shape Phase 11's own tests use."""
    (tmp_path / "widgets.py").write_text(
        '"""Widget module."""\n\n\n'
        "def helper(x):\n"
        '    """Doubles x."""\n'
        "    return x * 2\n\n\n"
        "class Widget:\n"
        '    """A widget."""\n\n'
        "    def render(self, x):\n"
        '        """Render the widget."""\n'
        "        return helper(x)\n"
    )
    scan_result = httpx.post(f"{knowledge_pipelines_url}/code-analysis/scan", json={"repo": str(tmp_path), "mode": "full_scan", "trigger": "human_admin"}, timeout=15.0)
    assert scan_result.status_code == 200
    return tmp_path


def test_review_check_callers_tool_call_returns_real_call_graph_data(full_stack, knowledge_pipelines_url, code_analysis_repo, monkeypatch):
    _ensure_ready(code_review_agent_register, full_stack["governance"], full_stack["assembly"])
    calls = {"count": 0}

    def fake_generate(model, prompt):
        calls["count"] += 1
        if calls["count"] == 1:
            return _stub("review.check_callers", target_repo=str(code_analysis_repo), symbol_ref="widgets.helper")
        assert "widgets.Widget.render" in prompt
        return _stub("review.approve_recommendation", target_repo="", answer_or_proposal="helper is called by Widget.render; no concern.", risk_classification="informational")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id=f"review-callers-test-{uuid.uuid4().hex[:8]}", task_description="Check what calls helper() in widgets.py.",
        agent_capability="code_review_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    db.close()

    assert execution.status == "completed"
    assert execution.iterations_used == 2
    assert execution.result.get("review_execution") == {"attempted": False, "reason": "no target_approval_id (or unrecognized action) — nothing to attach to"}


def test_review_fetch_diff_and_attach_to_real_pending_approval(
    full_stack, execution_url, proposal_repo, disposable_bare_repo_for_bridge, monkeypatch,
):
    """The full Phase 16 loop closes end to end: a REAL other agent's
    proposal is pending real human approval; Code Review Agent fetches
    the REAL diff of that branch, then attaches its assessment to that
    SAME real approval — confirmed by fetching the approval back from
    governance directly, not by trusting Reasoning Engine's own report."""
    _ensure_ready(code_review_agent_register, full_stack["governance"], full_stack["assembly"])

    # A real pending approval to attach to, exactly like any other
    # agent's own require_approval outcome would create.
    target_approval = httpx.post(
        f"{full_stack['governance']}/approval/request",
        json={"action": "manufacturing.propose_schedule_change", "requested_by": "manufacturing_agent"},
    ).json()
    target_approval_id = target_approval["id"]

    # A real branch with a real committed change to diff against.
    branch_name = f"code-review-agent-test-branch-{uuid.uuid4().hex[:8]}"
    subprocess.run(["git", "-C", str(proposal_repo), "checkout", "-b", branch_name], check=True, capture_output=True)
    (proposal_repo / "CHANGED.md").write_text("a real change to review\n")
    subprocess.run(["git", "-C", str(proposal_repo), "add", "CHANGED.md"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(proposal_repo), "-c", "user.email=test@test.local", "-c", "user.name=test", "commit", "-m", "a real change"],
        check=True, capture_output=True,
    )

    calls = {"count": 0}

    def fake_generate(model, prompt):
        calls["count"] += 1
        if calls["count"] == 1:
            return _stub("review.fetch_diff", target_repo=str(proposal_repo), target_branch=branch_name)
        assert "CHANGED.md" in prompt
        return _stub(
            "review.approve_recommendation", target_repo="", answer_or_proposal="Adds a new file, no caller impact.",
            risk_classification="informational", target_approval_id=target_approval_id,
        )

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id=f"review-diff-test-{uuid.uuid4().hex[:8]}", task_description=f"Review branch {branch_name} for approval {target_approval_id}.",
        agent_capability="code_review_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    db.close()

    assert execution.status == "completed"
    review_execution = execution.result["review_execution"]
    assert review_execution["attempted"] is True
    assert review_execution["result"]["ok"] is True

    fetched_approval = httpx.get(f"{full_stack['governance']}/approval/{target_approval_id}").json()
    reviews = fetched_approval["reviews"]
    assert len(reviews) == 1
    assert reviews[0]["reviewer_capability"] == "code_review_agent"
    assert reviews[0]["verdict"] == "recommend_approve"
    assert fetched_approval["status"] == "pending"  # the review never touches the human's own decision


# ---------------------------------------------------------------------------
# Reverse Engineering Agent — propose_documentation_draft materializes as
# a real git document AND chains into a real Documentation Engine ingest.
# ---------------------------------------------------------------------------

def test_reverse_eng_propose_documentation_draft_materializes_and_ingests_for_real(
    full_stack, execution_url, knowledge_pipelines_url, proposal_repo, disposable_bare_repo_for_bridge, monkeypatch,
):
    _ensure_ready(reverse_engineering_agent_register, full_stack["governance"], full_stack["assembly"])
    draft_text = "Reconstructed (inferred from call sites): `helper(x)` appears to double a quantity used by `Widget.render`."

    def fake_generate(model, prompt):
        return _stub("reverse_eng.propose_documentation_draft", answer_or_proposal=draft_text, risk_classification="medium")

    monkeypatch.setattr(loop, "generate", fake_generate)

    task_id = f"reverse-eng-test-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    execution = loop.execute(
        db, task_id=task_id, task_description="Draft documentation for the undocumented helper() function.",
        agent_capability="reverse_engineering_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    assert execution.status == "awaiting_approval"

    httpx.post(f"{full_stack['governance']}/approval/{execution.approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    resumed = loop.resume(db, execution.id)
    db.close()

    assert resumed.status == "completed"
    git_execution = resumed.result["git_execution"]
    assert git_execution["attempted"] is True
    branch_name = git_execution["branch_name"]
    assert branch_name == f"reverse-engineering-agent/task-{task_id}"

    show_output = subprocess.run(
        ["git", "show", f"{branch_name}:proposals/{task_id}.md"],
        cwd=str(disposable_bare_repo_for_bridge), capture_output=True, text=True,
    ).stdout
    assert draft_text in show_output

    docs_execution = resumed.result["docs_execution"]
    assert docs_execution["attempted"] is True
    assert docs_execution["result"]["ok"] is True
    document_id = docs_execution["result"]["document_id"]

    # Independently verify the real document via Documentation Engine's own sources listing.
    sources = httpx.get(f"{knowledge_pipelines_url}/docs/sources", params={"project_id": task_id}).json()["sources"]
    assert any(s["document_id"] == document_id for s in sources)


# ---------------------------------------------------------------------------
# Architecture Agent — needs zero new mechanism, reuses execution_bridge
# unchanged for architecture.propose_decision.
# ---------------------------------------------------------------------------

def test_architecture_propose_decision_materializes_as_a_real_git_document(
    full_stack, execution_url, proposal_repo, disposable_bare_repo_for_bridge, monkeypatch,
):
    _ensure_ready(architecture_agent_register, full_stack["governance"], full_stack["assembly"])
    proposal_text = "Adopt a shared review_bridge.py pattern for advisory agents rather than a bespoke channel per agent."

    def fake_generate(model, prompt):
        return _stub("architecture.propose_decision", answer_or_proposal=proposal_text, risk_classification="medium")

    monkeypatch.setattr(loop, "generate", fake_generate)

    task_id = f"architecture-test-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    execution = loop.execute(
        db, task_id=task_id, task_description="Propose a pattern for future advisory agents.",
        agent_capability="architecture_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    assert execution.status == "awaiting_approval"

    httpx.post(f"{full_stack['governance']}/approval/{execution.approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    resumed = loop.resume(db, execution.id)
    db.close()

    assert resumed.status == "completed"
    git_execution = resumed.result["git_execution"]
    assert git_execution["attempted"] is True
    branch_name = git_execution["branch_name"]
    assert branch_name == f"architecture-agent/task-{task_id}"

    show_output = subprocess.run(
        ["git", "show", f"{branch_name}:proposals/{task_id}.md"],
        cwd=str(disposable_bare_repo_for_bridge), capture_output=True, text=True,
    ).stdout
    assert proposal_text in show_output
    assert "docs_execution" not in resumed.result  # unlike reverse_eng, no chained ingest step


# ---------------------------------------------------------------------------
# Live-model smoke tests
# ---------------------------------------------------------------------------

_TERMINAL_STATES = ("completed", "awaiting_approval", "refused", "delegated", "awaiting_delegation", "failed")


@pytest.mark.parametrize("agent_capability,register_module,question", [
    ("code_review_agent", code_review_agent_register, "In one sentence, explain what a code review is for. Don't fetch any diff or check any callers."),
    ("reverse_engineering_agent", reverse_engineering_agent_register, "In one sentence, explain what reverse engineering code means. Don't propose any documentation draft."),
    ("architecture_agent", architecture_agent_register, "In one sentence, explain what an architectural decision record is. Don't propose any decision."),
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
