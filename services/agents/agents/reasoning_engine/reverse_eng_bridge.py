from agents import clients

# Phase 16: the one genuinely new materialization step this phase needed
# — reverse_eng.propose_documentation_draft reuses
# execution_bridge.materialize_propose_change() completely unchanged for
# the git-commit half, then this bridge closes the loop from inference
# to record by ingesting that SAME just-committed file into Documentation
# Engine's already-existing POST /docs/ingest (Phase 9).


def materialize_propose_documentation(execution, git_execution: dict) -> dict:
    """
    Called from resume() right after execution_bridge.materialize_propose_change()
    — only attempted if that git materialization actually reached a real
    committed file (stage reached at least "commit"); a proposal that
    never got committed has nothing on disk to ingest.
    """
    if not git_execution.get("attempted") or git_execution.get("stage") not in ("commit", "push", "open_mr"):
        return {"attempted": False, "reason": f"git materialization did not reach a committed file (stage={git_execution.get('stage')!r}) — nothing to ingest"}

    from agents.reasoning_engine import execution_bridge
    if not execution_bridge.PROPOSAL_REPO_PATH:
        return {"attempted": False, "reason": "PROPOSAL_REPO_PATH not configured"}

    path_or_url = f"{execution_bridge.PROPOSAL_REPO_PATH}/proposals/{execution.task_id}.md"
    ingest_result = clients.docs_ingest(
        path_or_url, project_id=execution.task_id, doc_type="markdown",
        requested_by=execution.agent_capability, correlation_id=execution.id,
    )
    return {"attempted": True, "result": ingest_result}
