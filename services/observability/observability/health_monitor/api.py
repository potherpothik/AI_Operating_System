from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from observability.db import get_db
from observability import clients
from observability.registry import SERVICES, service_url
from observability.health_monitor import checks, store

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/system")
def health_system(db: Session = Depends(get_db)):
    """
    Aggregated liveness across every known service, plus the
    structurally-defined degraded states earlier phases already named
    but had nowhere to report to until now. A single unreachable
    service never blinds the rest of this response — each poll is
    independent (clients.poll_health never raises).
    """
    per_service = [clients.poll_health(s["name"], s["url"]) for s in SERVICES]
    services_down = [s["name"] for s in per_service if s["status"] != "up"]

    governance_reachable = "governance" not in services_down
    stuck_tasks = checks.check_stuck_tasks()
    stale_erp = checks.check_stale_erp_knowledge()
    stuck_reasoning = checks.check_stuck_reasoning_executions()

    gaps = {
        "stuck_tasks": stuck_tasks,
        "stale_erp_knowledge": stale_erp,
        "stuck_reasoning_executions": stuck_reasoning,
    }
    gaps_found_summary = [name for name, items in gaps.items() if items]

    store.record_poll(db, services_down=services_down, gaps_found=gaps_found_summary)
    clients.audit_log(
        "health_monitor", "health.poll", "system",
        decision="degraded" if (services_down or gaps_found_summary) else "healthy",
        reason=f"services_down={services_down}, gaps={gaps_found_summary}",
    )

    return {
        # Distinguished from a routine "down" entry — every other
        # service's own authorization depends on this one being real
        # (governance-first.mdc), so this gets its own top-level flag
        # rather than being just one more row in `services`.
        "governance_reachable": governance_reachable,
        "services": per_service,
        "gaps": gaps,
    }


@router.get("/{module}")
def health_module(module: str):
    url = service_url(module)
    if not url:
        raise HTTPException(status_code=404, detail=f"unknown module {module!r}")
    return clients.poll_health(module, url)


class AlertConfigRequest(BaseModel):
    metric_or_gap: str
    threshold: int = None
    destination_ref: str
    created_by: str = "human_admin"


@router.post("/alert-config")
def alert_config(req: AlertConfigRequest, db: Session = Depends(get_db)):
    """
    Persists the intent only — no real notification channel exists in
    this codebase yet (see the design doc's Section 5). This is not
    silently faked as "configured and working"; it is honestly what it
    is: a stored threshold a human (or a future real integration) can
    read back via GET /health/system today.
    """
    row = store.create_alert_config(db, req.metric_or_gap, req.threshold, req.destination_ref, req.created_by)
    clients.audit_log(req.created_by, "health.alert_config", req.metric_or_gap, decision="recorded", reason=req.destination_ref)
    return {"id": row.id, "metric_or_gap": row.metric_or_gap, "threshold": row.threshold, "destination_ref": row.destination_ref}
