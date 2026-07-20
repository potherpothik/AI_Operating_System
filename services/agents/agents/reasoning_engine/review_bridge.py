from agents import clients

# Phase 16: Code Review Agent's two real, non-terminal tool calls,
# mirroring database_bridge.py's exact shape — review.fetch_diff calls
# Git Manager's existing read-only /git/diff (Phase 6), review.check_callers
# calls Code Analysis Engine's existing, unauthenticated GET /symbol/{ref}
# (Phase 11). Both feed a REAL result back into context for the model's
# next turn, rather than trusting a guess about what a diff contains or
# who calls a given symbol.
TOOL_ACTIONS = {"review.fetch_diff", "review.check_callers"}

# Terminal actions: never require human approval themselves (the doc's
# own framing — "its own output is advisory, feeding INTO approval
# rather than bypassing it") — but when the model names a real
# target_approval_id, execute() attaches the assessment synchronously,
# no resume()/approval step needed for Code Review Agent's own output.
REVIEW_ATTACH_ACTIONS = {"review.flag_concern", "review.approve_recommendation"}

_VERDICT_BY_ACTION = {
    "review.flag_concern": "concern",
    "review.approve_recommendation": "recommend_approve",
}


def handle_tool_call(parsed: dict, agent_capability: str, task_id: str, correlation_id: str = None) -> dict:
    action = parsed.get("action")

    if action == "review.fetch_diff":
        repo = (parsed.get("target_repo") or "").strip()
        if not repo:
            return {"summary": "target_repo was empty — nothing to diff"}
        target_branch = (parsed.get("target_branch") or "").strip()
        # A bare branch name alone (`git diff <branch>`) compares that
        # branch's tip to the CURRENT working tree, not to main — usually
        # empty right after a clean checkout, since nothing's uncommitted.
        # What "review the real change on this branch" actually means is
        # a comparison against main, so build that range automatically
        # rather than pushing git range syntax onto the model.
        args = [f"main...{target_branch}"] if target_branch else []
        result = clients.git_diff(repo, agent_capability, task_id, "reasoning_engine", args=args, correlation_id=correlation_id or "")
        if not result.get("ok"):
            return {"summary": f"diff fetch failed: {result.get('error')}"}
        diff_text = (result.get("diff") or "")[:4000]
        return {"summary": f"real diff for {args or '(working tree)'}: {diff_text}"}

    if action == "review.check_callers":
        repo = (parsed.get("target_repo") or "").strip()
        symbol_ref = (parsed.get("symbol_ref") or "").strip()
        if not repo or not symbol_ref:
            return {"summary": "target_repo and symbol_ref are both required to check callers"}
        # GET /graph, not GET /symbol/{ref} — that endpoint's own
        # callers/callees lists are raw internal ids, not names a model
        # (or a human reading its final assessment) can reason about;
        # /graph already resolves edges to real qualified names.
        result = clients.code_analysis_get_graph(repo)
        if not result.get("ok"):
            return {"summary": f"call graph lookup failed: {result.get('error')}"}
        if symbol_ref not in result.get("nodes", []):
            return {"summary": f"{symbol_ref!r} was not found in the analyzed repo's call graph — check the exact qualified name (e.g. 'module.function' or 'module.Class.method')"}
        callers = [e["from"] for e in result.get("edges", []) if e["to"] == symbol_ref]
        return {"summary": f"{symbol_ref!r} has {len(callers)} real caller(s) in the analyzed repo: {callers}"}

    return {"summary": f"unrecognized tool action {action!r}"}


def materialize_attach_review(execution) -> dict:
    """
    Called directly from execute()'s finalize step (not resume() — Code
    Review Agent's own actions never require approval) when the model's
    response named a real target_approval_id. Never touches the target
    approval's own status/decision — purely additive context for the
    human approver (governance/approval/api.py's attach_review).
    """
    result = execution.result or {}
    action = result.get("action")
    target_approval_id = (result.get("target_approval_id") or "").strip()
    verdict = _VERDICT_BY_ACTION.get(action)
    if not target_approval_id or not verdict:
        return {"attempted": False, "reason": "no target_approval_id (or unrecognized action) — nothing to attach to"}

    attach_result = clients.attach_review(
        target_approval_id, execution.agent_capability, verdict,
        result.get("answer_or_proposal", ""), correlation_id=execution.id,
    )
    return {"attempted": True, "result": attach_result}
