from pathlib import Path

from knowledge_pipelines import clients
from knowledge_pipelines.code_analysis_engine import store, classifier


class RequestDenied(Exception):
    pass


class NotApprovedYet(Exception):
    pass


class ModelNotLocal(Exception):
    pass


def request_raw_source(db, task_id: str, requesting_capability: str, repo: str, files: list[str], reason: str, target_model: str) -> dict:
    """
    The concrete mechanism behind the mandate's single most emphasized
    confidentiality rule (Phase 11 doc, Section 1: Logging). Every
    request is logged in full here — files, agent, reason — regardless
    of outcome, before any approval decision exists yet.
    """
    decision = clients.authorize(requesting_capability, "code_analysis.raw_source_request", repo)
    if decision["decision"] == "deny":
        clients.audit_log(
            requesting_capability, "code_analysis.raw_source_request", repo, decision="deny",
            reason=decision.get("reason", ""), correlation_id=task_id,
        )
        raise RequestDenied(decision.get("reason", "denied by security layer"))

    approval = clients.request_approval(
        action="code_analysis.raw_source_request", requested_by=requesting_capability,
        risk_tier="high", payload_ref=f"{repo}: {', '.join(files)} — {reason}",
    )
    req = store.create_raw_source_request(db, task_id, requesting_capability, repo, files, reason, target_model, approval.get("id"))
    clients.audit_log(
        requesting_capability, "code_analysis.raw_source_request", repo, decision="pending_approval",
        reason=f"files={files}, reason={reason!r}, approval_id={approval.get('id')}", correlation_id=task_id,
    )
    return {"request_id": req.id, "status": "pending_approval", "approval_id": approval.get("id")}


def fetch_raw_source(db, request_id: str) -> dict:
    """
    The second half of the two-step gate. Re-verifies BOTH preconditions
    fresh at fetch time, not just at request time — an approval can be
    minutes or hours old, and target_model's local status is checked
    again here rather than trusted from whatever was true when the
    request was filed (Phase 11 doc, Section 1: Security — "re-verify
    the target model is local-only... at its strictest").
    """
    req = store.get_raw_source_request(db, request_id)
    if not req:
        raise store.NotFound(f"raw_source_request {request_id!r} not found")

    approval = clients.get_approval_status(req.approval_id)
    if approval.get("status") != "approved":
        clients.audit_log(
            req.requesting_capability, "code_analysis.raw_source_request.fetch", req.repo,
            decision=approval.get("status", "unknown"), correlation_id=req.task_id,
        )
        return {"status": approval.get("status", "unknown")}

    ceiling = clients.model_ceiling(req.target_model)
    if classifier.tier_index(ceiling["ceiling"]) < classifier.tier_index(classifier.RAW_SOURCE_CLASSIFICATION):
        store.mark_denied(db, req)
        clients.audit_log(
            req.requesting_capability, "code_analysis.raw_source_request.fetch", req.repo, decision="deny",
            reason=f"target_model {req.target_model!r} ceiling={ceiling['ceiling']!r}, below confidential", correlation_id=req.task_id,
        )
        raise ModelNotLocal(f"{req.target_model!r} is not a local model — refusing to release raw source to it")

    root = Path(req.repo)
    contents = {f: (root / f).read_text(encoding="utf-8") for f in req.files}
    store.mark_fulfilled(db, req)
    clients.audit_log(
        req.requesting_capability, "code_analysis.raw_source_request.fetch", req.repo, decision="fulfilled",
        reason=f"files={req.files}, approval_id={req.approval_id}", correlation_id=req.task_id,
    )
    return {"status": "fulfilled", "files": contents, "classification": classifier.RAW_SOURCE_CLASSIFICATION}
