import subprocess
import pytest
from fastapi import HTTPException

from execution.db import SessionLocal
from execution.git_manager import api as git_api
from execution.git_manager import branch_policy


def _log_output(work_dir, *args):
    return subprocess.run(["git", "-C", str(work_dir)] + list(args), capture_output=True, text=True).stdout


def test_branch_creates_real_agent_named_branch(cloned_repo, governance_url):
    db = SessionLocal()
    result = git_api.branch(
        git_api.BranchRequest(repo=str(cloned_repo), agent_capability="odoo_agent", task_id="task-1", requesting_agent="reasoning_engine"),
        db,
    )
    db.close()

    assert result["status"] == "completed"
    assert result["branch_name"] == "odoo-agent/task-task-1"
    current_branch = _log_output(cloned_repo, "branch", "--show-current").strip()
    assert current_branch == "odoo-agent/task-task-1"


def test_branch_rejects_unsafe_task_id_before_touching_git(cloned_repo, governance_url):
    db = SessionLocal()
    with pytest.raises(Exception):
        git_api.branch(
            git_api.BranchRequest(repo=str(cloned_repo), agent_capability="odoo_agent", task_id="1; rm -rf /", requesting_agent="reasoning_engine"),
            db,
        )
    db.close()
    # still on main — the malformed task_id never reached git at all
    assert _log_output(cloned_repo, "branch", "--show-current").strip() == "main"


def test_commit_creates_real_commit_with_provenance_trailer(cloned_repo, governance_url):
    db = SessionLocal()
    git_api.branch(
        git_api.BranchRequest(repo=str(cloned_repo), agent_capability="odoo_agent", task_id="task-2", requesting_agent="reasoning_engine"),
        db,
    )
    (cloned_repo / "proposed_change.txt").write_text("agent-proposed content\n")

    result = git_api.commit(
        git_api.CommitRequest(
            repo=str(cloned_repo), agent_capability="odoo_agent", task_id="task-2", requesting_agent="reasoning_engine",
            files_changed=["proposed_change.txt"], summary="Propose invoice threshold change",
            reasoning_execution_id="exec-1", context_id="ctx-1",
        ),
        db,
    )
    db.close()

    assert result["status"] == "completed"
    assert result["commit_sha"]
    commit_body = _log_output(cloned_repo, "log", "-1", "--format=%B")
    assert "Propose invoice threshold change" in commit_body
    assert "Task-Id: task-2" in commit_body
    assert "Agent-Capability: odoo_agent" in commit_body
    assert "Context-Id: ctx-1" in commit_body
    assert "Reasoning-Execution-Id: exec-1" in commit_body


def test_commit_triggers_code_analysis_scan_with_the_real_files_changed_list(cloned_repo, governance_url, monkeypatch):
    """
    Phase 11's on_commit trigger — fired from inside commit() itself
    using the SAME files_changed list the request already carried, not
    a separate git-diff call. Monkeypatches the actual HTTP call
    (clients.trigger_code_analysis_scan) rather than running a live Code
    Analysis Engine here, since that belongs to knowledge_pipelines'
    own test suite — what's under test here is that Git Manager calls it
    at all, with the right arguments, not Code Analysis Engine's own
    scanning logic.
    """
    from execution.git_manager import api as git_api_module

    calls = []
    monkeypatch.setattr(
        git_api_module.clients, "trigger_code_analysis_scan",
        lambda repo, files, commit_ref: calls.append({"repo": repo, "files": files, "commit_ref": commit_ref}) or {"attempted": True},
    )

    db = SessionLocal()
    git_api.branch(
        git_api.BranchRequest(repo=str(cloned_repo), agent_capability="odoo_agent", task_id="task-scan-1", requesting_agent="reasoning_engine"),
        db,
    )
    (cloned_repo / "proposed_change.py").write_text("def f():\n    return 1\n")
    result = git_api.commit(
        git_api.CommitRequest(
            repo=str(cloned_repo), agent_capability="odoo_agent", task_id="task-scan-1", requesting_agent="reasoning_engine",
            files_changed=["proposed_change.py"], summary="Add a function",
        ),
        db,
    )
    db.close()

    assert len(calls) == 1
    assert calls[0]["repo"] == str(cloned_repo)
    assert calls[0]["files"] == ["proposed_change.py"]
    assert calls[0]["commit_ref"] == result["commit_sha"]


def test_code_analysis_trigger_is_a_real_no_op_when_unconfigured():
    """CODE_ANALYSIS_URL unset (the default in this environment) means
    the trigger returns cleanly without ever attempting an HTTP call —
    confirmed by NOT monkeypatching httpx here at all; a real network
    attempt with nothing listening would raise, not return quietly."""
    from execution import clients as clients_module

    assert clients_module.CODE_ANALYSIS_URL is None
    result = clients_module.trigger_code_analysis_scan("/tmp/some/repo", ["a.py"], "deadbeef")
    assert result == {"attempted": False, "reason": "CODE_ANALYSIS_URL not configured"}


def test_commit_uses_distinct_agent_identity_not_host_identity(cloned_repo, governance_url):
    db = SessionLocal()
    git_api.branch(
        git_api.BranchRequest(repo=str(cloned_repo), agent_capability="odoo_agent", task_id="task-3", requesting_agent="reasoning_engine"),
        db,
    )
    (cloned_repo / "f.txt").write_text("x\n")
    git_api.commit(
        git_api.CommitRequest(
            repo=str(cloned_repo), agent_capability="odoo_agent", task_id="task-3", requesting_agent="reasoning_engine",
            files_changed=["f.txt"], summary="test commit",
        ),
        db,
    )
    db.close()

    author = _log_output(cloned_repo, "log", "-1", "--format=%an <%ae>").strip()
    assert author == "Odoo Agent <agent+odoo_agent@ai-orchestration.local>"

    host_email = subprocess.run(["git", "config", "--global", "user.email"], capture_output=True, text=True).stdout.strip()
    if host_email:
        assert host_email not in author


def test_diff_shows_real_staged_changes(cloned_repo, governance_url):
    db = SessionLocal()
    git_api.branch(
        git_api.BranchRequest(repo=str(cloned_repo), agent_capability="odoo_agent", task_id="task-4", requesting_agent="reasoning_engine"),
        db,
    )
    (cloned_repo / "README.md").write_text("initial\nmodified by agent\n")
    result = git_api.diff(
        git_api.DiffRequest(repo=str(cloned_repo), agent_capability="odoo_agent", requesting_agent="reasoning_engine", task_id="task-4"),
        db,
    )
    db.close()
    assert "modified by agent" in result["diff"]


def test_push_lands_commit_in_the_disposable_remote(cloned_repo, disposable_bare_repo, governance_url):
    db = SessionLocal()
    git_api.branch(
        git_api.BranchRequest(repo=str(cloned_repo), agent_capability="odoo_agent", task_id="task-5", requesting_agent="reasoning_engine"),
        db,
    )
    (cloned_repo / "f.txt").write_text("pushed content\n")
    commit_result = git_api.commit(
        git_api.CommitRequest(
            repo=str(cloned_repo), agent_capability="odoo_agent", task_id="task-5", requesting_agent="reasoning_engine",
            files_changed=["f.txt"], summary="a real pushed commit",
        ),
        db,
    )
    push_result = git_api.push(
        git_api.PushRequest(
            repo=str(cloned_repo), agent_capability="odoo_agent", task_id="task-5", requesting_agent="reasoning_engine",
            branch_name="odoo-agent/task-task-5",
        ),
        db,
    )
    db.close()

    assert push_result["status"] == "completed"
    # Independent verification: ask the bare "remote" itself, not the working clone.
    remote_branches = subprocess.run(["git", "branch", "-r"], cwd=str(disposable_bare_repo), capture_output=True, text=True)
    # bare repos don't have -r in the same way; verify via for-each-ref instead
    refs = subprocess.run(["git", "for-each-ref", "--format=%(refname)"], cwd=str(disposable_bare_repo), capture_output=True, text=True).stdout
    assert "refs/heads/odoo-agent/task-task-5" in refs
    remote_log = subprocess.run(
        ["git", "log", "-1", "--format=%H", "odoo-agent/task-task-5"], cwd=str(disposable_bare_repo), capture_output=True, text=True
    ).stdout.strip()
    assert remote_log == commit_result["commit_sha"]


def test_push_to_protected_branch_rejected_before_reaching_shell_executor(cloned_repo, disposable_bare_repo, governance_url):
    db = SessionLocal()
    with pytest.raises(HTTPException) as exc_info:
        git_api.push(
            git_api.PushRequest(
                repo=str(cloned_repo), agent_capability="odoo_agent", task_id="task-6", requesting_agent="reasoning_engine",
                branch_name="main",
            ),
            db,
        )
    db.close()
    assert exc_info.value.status_code == 403

    # main on the real remote must be completely untouched
    remote_main_log = subprocess.run(
        ["git", "log", "-1", "--format=%s", "main"], cwd=str(disposable_bare_repo), capture_output=True, text=True
    ).stdout.strip()
    assert remote_main_log == "initial commit"


def test_push_to_a_different_agents_namespace_rejected(cloned_repo, governance_url):
    db = SessionLocal()
    with pytest.raises(HTTPException) as exc_info:
        git_api.push(
            git_api.PushRequest(
                repo=str(cloned_repo), agent_capability="odoo_agent", task_id="task-7", requesting_agent="reasoning_engine",
                branch_name="django-agent/task-hijack",
            ),
            db,
        )
    db.close()
    assert exc_info.value.status_code == 403


def test_open_mr_reports_not_configured_without_github_token(cloned_repo, governance_url, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    db = SessionLocal()
    result = git_api.open_mr(
        git_api.OpenMrRequest(
            repo="potherpothik/does-not-matter-for-this-test", branch_name="odoo-agent/task-8",
            agent_capability="odoo_agent", task_id="task-8", requesting_agent="reasoning_engine",
            proposal_text="Lower the invoice approval threshold.", risk_classification="medium",
            files_changed=["addons/odoo/invoice.py"],
        ),
        db,
    )
    db.close()
    assert result["status"] == "not_configured"


def test_full_propose_change_flow_branch_commit_push_open_mr(cloned_repo, disposable_bare_repo, governance_url, monkeypatch):
    """
    The Phase 6 doc's Section 3 end-to-end diagram, exercised against a
    real disposable repo: branch -> commit (real provenance trailer) ->
    push (lands in the real remote) -> open_mr (reports not_configured
    cleanly, since no real GitHub token exists here — never silently
    treated as success).
    """
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    db = SessionLocal()

    branch_result = git_api.branch(
        git_api.BranchRequest(repo=str(cloned_repo), agent_capability="odoo_agent", task_id="task-9", requesting_agent="reasoning_engine"),
        db,
    )
    (cloned_repo / "invoice_rule.txt").write_text("Invoices over $2000 require manager approval.\n")
    commit_result = git_api.commit(
        git_api.CommitRequest(
            repo=str(cloned_repo), agent_capability="odoo_agent", task_id="task-9", requesting_agent="reasoning_engine",
            files_changed=["invoice_rule.txt"], summary="Lower invoice approval threshold to $2000",
            reasoning_execution_id="exec-9", context_id="ctx-9",
        ),
        db,
    )
    push_result = git_api.push(
        git_api.PushRequest(
            repo=str(cloned_repo), agent_capability="odoo_agent", task_id="task-9", requesting_agent="reasoning_engine",
            branch_name=branch_result["branch_name"],
        ),
        db,
    )
    mr_result = git_api.open_mr(
        git_api.OpenMrRequest(
            repo="potherpothik/AI_Operating_System", branch_name=branch_result["branch_name"],
            agent_capability="odoo_agent", task_id="task-9", requesting_agent="reasoning_engine",
            proposal_text="Lower the invoice approval threshold from $5000 to $2000.",
            risk_classification="medium", files_changed=["invoice_rule.txt"],
        ),
        db,
    )
    db.close()

    assert branch_result["status"] == "completed"
    assert commit_result["status"] == "completed"
    assert push_result["status"] == "completed"
    assert mr_result["status"] == "not_configured"  # honest about the real boundary, not a fake success
