import os
import httpx

SECURITY_LAYER_URL = os.environ.get("SECURITY_LAYER_URL", "http://localhost:8000")
CODE_ANALYSIS_URL = os.environ.get("CODE_ANALYSIS_URL")  # unset = Phase 11's on_commit trigger is simply skipped


def authorize(actor: str, action: str, resource: str, correlation_id: str = "") -> dict:
    try:
        resp = httpx.post(
            f"{SECURITY_LAYER_URL}/security/authorize",
            json={"actor": actor, "actor_type": "agent", "action": action, "resource": resource, "correlation_id": correlation_id},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:  # noqa: BLE001 — fail closed: an unreachable Security Layer must never be read as "allow"
        return {"decision": "deny", "reason": f"security layer unreachable, failing closed: {e}"}


def audit_log(actor_id: str, action: str, resource: str, decision: str = "recorded", reason: str = "", correlation_id: str = "") -> bool:
    try:
        resp = httpx.post(
            f"{SECURITY_LAYER_URL}/audit/log",
            json={
                "actor_id": actor_id, "actor_type": "service", "action": action, "resource": resource,
                "decision": decision, "reason": reason, "correlation_id": correlation_id,
            },
            timeout=10.0,
        )
        return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def trigger_code_analysis_scan(repo: str, files: list[str], commit_ref: str = None) -> dict:
    """
    Phase 11's on_commit trigger (Section 1: "Incremental analysis
    triggered on commit"), fired from git_manager/api.py's own commit
    endpoint after a real commit lands — using the SAME files_changed
    list the commit request already carried, not a separate git-diff
    call this service would otherwise need to make itself. Best-effort
    and never allowed to affect the commit's own outcome: if
    CODE_ANALYSIS_URL isn't configured or Code Analysis Engine is
    unreachable, the commit still succeeds — this is a real loop closed
    when possible, not a hard dependency (same posture as
    PROPOSAL_REPO_PATH being unset elsewhere in this codebase).
    """
    if not CODE_ANALYSIS_URL:
        return {"attempted": False, "reason": "CODE_ANALYSIS_URL not configured"}
    try:
        resp = httpx.post(
            f"{CODE_ANALYSIS_URL}/code-analysis/scan",
            json={"repo": repo, "mode": "incremental", "files": files, "commit_ref": commit_ref, "trigger": "git_manager"},
            timeout=30.0,
        )
        resp.raise_for_status()
        return {"attempted": True, "result": resp.json()}
    except Exception as e:  # noqa: BLE001
        return {"attempted": True, "failed": True, "reason": str(e)}
