import os
from pathlib import Path

from agents import clients

PROPOSAL_REPO_PATH = os.environ.get("PROPOSAL_REPO_PATH")  # a real working_dir under execution's SANDBOX_ROOT
PROPOSAL_MR_REPO = os.environ.get("PROPOSAL_MR_REPO", "")  # "owner/repo" for the forge adapter


def materialize_propose_change(execution) -> dict:
    """
    Turns an approved odoo.propose_change into a real branch, commit,
    push, and (attempted) MR via the Phase 6 execution service — closing
    the Phase 6 doc's Section 3 end-to-end diagram.

    Honest boundary: this commits the model's proposal TEXT as a review
    document (proposals/{task_id}.md), not a computed code diff. Odoo
    Agent (Phase 5) was never asked to produce an actual patch — its
    output schema has answer_or_proposal as prose, not a diff — so there
    is nothing else here to commit yet. A future business-agent phase
    that returns real file diffs could extend this to write those files
    directly instead. Documented in services/agents/README.md.
    """
    if not PROPOSAL_REPO_PATH:
        return {"attempted": False, "reason": "PROPOSAL_REPO_PATH not configured"}

    result = execution.result or {}
    proposal_text = result.get("answer_or_proposal", "")
    risk = result.get("risk_classification", "medium")
    task_id = execution.task_id
    agent_capability = execution.agent_capability

    branch_result = clients.git_branch(PROPOSAL_REPO_PATH, agent_capability, task_id, "reasoning_engine", correlation_id=execution.id)
    if branch_result.get("status") != "completed":
        return {"attempted": True, "stage": "branch", "result": branch_result}
    branch_name = branch_result["branch_name"]

    file_rel_path = f"proposals/{task_id}.md"
    file_abs_path = Path(PROPOSAL_REPO_PATH) / file_rel_path
    file_abs_path.parent.mkdir(parents=True, exist_ok=True)
    file_abs_path.write_text(proposal_text + "\n")

    commit_result = clients.git_commit(
        PROPOSAL_REPO_PATH, agent_capability, task_id, "reasoning_engine", [file_rel_path],
        summary=f"Propose change for task {task_id}",
        reasoning_execution_id=execution.id, context_id=execution.context_id, correlation_id=execution.id,
    )
    if commit_result.get("status") != "completed":
        return {"attempted": True, "stage": "commit", "result": commit_result}

    push_result = clients.git_push(PROPOSAL_REPO_PATH, agent_capability, task_id, "reasoning_engine", branch_name, correlation_id=execution.id)
    if push_result.get("status") != "completed":
        return {"attempted": True, "stage": "push", "result": push_result}

    mr_result = clients.git_open_mr(
        PROPOSAL_MR_REPO, branch_name, agent_capability, task_id, "reasoning_engine",
        proposal_text=proposal_text, risk_classification=risk, files_changed=[file_rel_path], correlation_id=execution.id,
    )

    return {
        "attempted": True, "stage": "open_mr", "branch_name": branch_name,
        "commit_sha": commit_result.get("commit_sha"), "mr_result": mr_result,
    }
