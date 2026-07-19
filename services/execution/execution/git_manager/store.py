from sqlalchemy.orm import Session

from execution.git_manager.models import GitAction


def record(db: Session, action: str, repo: str, agent_capability: str, task_id: str = None,
           reasoning_execution_id: str = None, context_id: str = None, branch_name: str = None,
           commit_sha: str = None, mr_ref: str = None, provenance_trailer: str = None,
           result: dict = None, status: str = "completed") -> GitAction:
    row = GitAction(
        task_id=task_id, reasoning_execution_id=reasoning_execution_id, context_id=context_id,
        action=action, repo=repo, agent_capability=agent_capability, branch_name=branch_name,
        commit_sha=commit_sha, mr_ref=mr_ref, provenance_trailer=provenance_trailer,
        result=result, status=status,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get(db: Session, git_action_id: str) -> GitAction | None:
    return db.query(GitAction).filter(GitAction.id == git_action_id).first()


def list_for_task(db: Session, task_id: str) -> list[GitAction]:
    return db.query(GitAction).filter(GitAction.task_id == task_id).order_by(GitAction.created_at.asc()).all()
