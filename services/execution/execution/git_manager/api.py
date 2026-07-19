from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from execution.db import get_db
from execution import clients
from execution.git_manager import branch_policy, provenance, codeowners, store
from execution.git_manager.forge_adapter.github import GitHubAdapter, GitHubNotConfigured
from execution.shell_executor.service import run_sandboxed, Denied

router = APIRouter(prefix="/git", tags=["git"])


def _authorize_or_raise(agent_capability: str, action: str, resource: str, correlation_id: str):
    decision = clients.authorize(actor=agent_capability, action=action, resource=resource, correlation_id=correlation_id or "")
    if decision["decision"] == "deny":
        clients.audit_log(actor_id=agent_capability, action=action, resource=resource, decision="deny", reason=decision.get("reason", ""), correlation_id=correlation_id or "")
        raise HTTPException(status_code=403, detail=decision.get("reason", f"{action} denied by security layer"))


def _action_out(row) -> dict:
    return {
        "id": row.id, "action": row.action, "repo": row.repo, "branch_name": row.branch_name,
        "commit_sha": row.commit_sha, "mr_ref": row.mr_ref, "status": row.status,
        "result": row.result, "created_at": row.created_at.isoformat(),
    }


class BranchRequest(BaseModel):
    repo: str  # working_dir on disk (Shell Executor's sandbox root)
    agent_capability: str
    task_id: str
    requesting_agent: str
    correlation_id: str = None


@router.post("/branch")
def branch(req: BranchRequest, db: Session = Depends(get_db)):
    _authorize_or_raise(req.agent_capability, "git.branch", req.repo, req.correlation_id)

    branch_name = branch_policy.agent_branch_name(req.agent_capability, req.task_id)
    branch_policy.assert_not_protected(branch_name)  # cheap defense-in-depth; always true by construction

    try:
        execution = run_sandboxed(
            db, "git", ["checkout", "-b", branch_name], req.repo, req.agent_capability, req.requesting_agent,
            task_id=req.task_id, mode="mutating", correlation_id=req.correlation_id,
        )
    except Denied as e:
        raise HTTPException(status_code=403, detail=str(e))

    status = "completed" if execution.exit_code == 0 else "failed"
    row = store.record(
        db, "branch", req.repo, req.agent_capability, task_id=req.task_id,
        branch_name=branch_name, result={"exit_code": execution.exit_code, "stderr": execution.stderr}, status=status,
    )
    clients.audit_log(actor_id=req.agent_capability, action="git.branch", resource=branch_name, decision=status, correlation_id=req.correlation_id or "")
    return _action_out(row)


class CommitRequest(BaseModel):
    repo: str
    agent_capability: str
    task_id: str
    requesting_agent: str
    files_changed: list[str]
    summary: str
    reasoning_execution_id: str = None
    context_id: str = None
    correlation_id: str = None


@router.post("/commit")
def commit(req: CommitRequest, db: Session = Depends(get_db)):
    _authorize_or_raise(req.agent_capability, "git.commit", req.repo, req.correlation_id)

    trailer = provenance.build_trailer(req.task_id, req.agent_capability, req.context_id, req.reasoning_execution_id)
    message = provenance.build_commit_message(
        req.summary, req.task_id, req.agent_capability, context_id=req.context_id, reasoning_execution_id=req.reasoning_execution_id,
    )

    try:
        add_execution = run_sandboxed(
            db, "git", ["add"] + req.files_changed, req.repo, req.agent_capability, req.requesting_agent,
            task_id=req.task_id, mode="mutating", correlation_id=req.correlation_id,
        )
        if add_execution.exit_code != 0:
            row = store.record(db, "commit", req.repo, req.agent_capability, task_id=req.task_id, result={"stage": "add", "stderr": add_execution.stderr}, status="failed")
            return _action_out(row)

        commit_execution = run_sandboxed(
            db, "git", ["commit", "-m", message], req.repo, req.agent_capability, req.requesting_agent,
            task_id=req.task_id, mode="mutating", correlation_id=req.correlation_id,
            extra_env=provenance.agent_git_identity(req.agent_capability),
        )
        if commit_execution.exit_code != 0:
            row = store.record(db, "commit", req.repo, req.agent_capability, task_id=req.task_id, result={"stage": "commit", "stderr": commit_execution.stderr}, status="failed")
            return _action_out(row)

        sha_execution = run_sandboxed(
            db, "git", ["rev-parse", "HEAD"], req.repo, req.agent_capability, req.requesting_agent,
            task_id=req.task_id, mode="read_only", correlation_id=req.correlation_id,
        )
    except Denied as e:
        raise HTTPException(status_code=403, detail=str(e))

    commit_sha = (sha_execution.stdout or "").strip()
    row = store.record(
        db, "commit", req.repo, req.agent_capability, task_id=req.task_id,
        commit_sha=commit_sha, provenance_trailer=trailer,
        reasoning_execution_id=req.reasoning_execution_id, context_id=req.context_id,
        result={"exit_code": 0}, status="completed",
    )
    clients.audit_log(actor_id=req.agent_capability, action="git.commit", resource=commit_sha, decision="completed", correlation_id=req.correlation_id or "")
    return _action_out(row)


class DiffRequest(BaseModel):
    repo: str
    agent_capability: str
    requesting_agent: str
    args: list[str] = []
    task_id: str = None
    correlation_id: str = None


@router.post("/diff")
def diff(req: DiffRequest, db: Session = Depends(get_db)):
    # Read-only — no Human Approval Layer interaction (Phase 6 doc: "POST
    # /git/diff — Read-only diff, no approval needed"). Still authorized
    # and audited like everything else.
    _authorize_or_raise(req.agent_capability, "git.diff", req.repo, req.correlation_id)
    try:
        execution = run_sandboxed(
            db, "git", ["diff"] + req.args, req.repo, req.agent_capability, req.requesting_agent,
            task_id=req.task_id, mode="read_only", correlation_id=req.correlation_id,
        )
    except Denied as e:
        raise HTTPException(status_code=403, detail=str(e))
    return {"diff": execution.stdout, "exit_code": execution.exit_code}


class PushRequest(BaseModel):
    repo: str
    agent_capability: str
    task_id: str
    requesting_agent: str
    branch_name: str
    correlation_id: str = None


@router.post("/push")
def push(req: PushRequest, db: Session = Depends(get_db)):
    # Structural check FIRST, inside Git Manager itself, before this ever
    # reaches Shell Executor — defense in depth, not reliance on Security
    # Layer or the command allowlist alone (Phase 6 doc, Failure handling).
    try:
        branch_policy.assert_push_target_is_own_branch(req.branch_name, req.agent_capability)
    except branch_policy.ProtectedBranchError as e:
        clients.audit_log(actor_id=req.agent_capability, action="git.push", resource=req.branch_name, decision="deny", reason=str(e), correlation_id=req.correlation_id or "")
        raise HTTPException(status_code=403, detail=str(e))

    _authorize_or_raise(req.agent_capability, "git.push", req.branch_name, req.correlation_id)

    try:
        execution = run_sandboxed(
            db, "git", ["push", "origin", req.branch_name], req.repo, req.agent_capability, req.requesting_agent,
            task_id=req.task_id, mode="mutating", correlation_id=req.correlation_id,
        )
    except Denied as e:
        raise HTTPException(status_code=403, detail=str(e))

    status = "completed" if execution.exit_code == 0 else "failed"
    row = store.record(
        db, "push", req.repo, req.agent_capability, task_id=req.task_id,
        branch_name=req.branch_name, result={"exit_code": execution.exit_code, "stderr": execution.stderr}, status=status,
    )
    clients.audit_log(actor_id=req.agent_capability, action="git.push", resource=req.branch_name, decision=status, correlation_id=req.correlation_id or "")
    return _action_out(row)


class OpenMrRequest(BaseModel):
    repo: str  # "owner/repo" for the forge adapter — distinct from the local working_dir used by branch/commit/push
    base: str = "main"
    branch_name: str
    agent_capability: str
    task_id: str
    requesting_agent: str
    proposal_text: str
    risk_classification: str
    files_changed: list[str] = []
    correlation_id: str = None


@router.post("/open_mr")
def open_mr(req: OpenMrRequest, db: Session = Depends(get_db)):
    branch_policy.assert_not_protected(req.branch_name)
    _authorize_or_raise(req.agent_capability, "git.open_mr", req.repo, req.correlation_id)

    owners = codeowners.owners_for_files(req.files_changed)
    title = f"[{req.agent_capability}] {req.task_id}"
    body = (
        f"{req.proposal_text}\n\n"
        f"**Risk classification:** {req.risk_classification}\n"
        f"**Reviewers (CODEOWNERS):** {', '.join(sorted(owners)) or '(none matched)'}\n\n"
        f"---\n{provenance.build_trailer(req.task_id, req.agent_capability, None, None)}"
    )

    adapter = GitHubAdapter()
    try:
        result = adapter.open_pr(req.repo, req.base, req.branch_name, title, body)
        status = "completed"
    except GitHubNotConfigured as e:
        result = {"reason": str(e)}
        status = "not_configured"
    except Exception as e:  # noqa: BLE001 — a forge-side failure shouldn't crash the endpoint, it should report cleanly
        result = {"reason": str(e)}
        status = "failed"

    row = store.record(
        db, "open_mr", req.repo, req.agent_capability, task_id=req.task_id,
        branch_name=req.branch_name, mr_ref=result.get("url"), result=result, status=status,
    )
    clients.audit_log(actor_id=req.agent_capability, action="git.open_mr", resource=req.branch_name, decision=status, correlation_id=req.correlation_id or "")
    return _action_out(row)
