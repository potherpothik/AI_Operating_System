from typing import Optional
from fastapi import APIRouter, HTTPException

from observability import clients
from observability.metrics_dashboard import aggregator

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/overview")
def overview(since: Optional[str] = None, viewer: str = "human_admin"):
    clients.audit_log(viewer, "metrics.read", "overview")
    return aggregator.overview(since)


@router.get("/export")
def export(since: Optional[str] = None, viewer: str = "human_admin"):
    """Same payload as /overview today — a distinct endpoint per the
    doc's own API table, since a real external dashboard tool would want
    a stable export contract independent of whatever /overview's
    human-facing shape evolves into."""
    clients.audit_log(viewer, "metrics.export", "all")
    return aggregator.overview(since)


@router.get("/{category}")
def get_category(category: str, since: Optional[str] = None, viewer: str = "human_admin"):
    result = aggregator.category(category, since)
    if result is None:
        raise HTTPException(status_code=404, detail=f"unknown category {category!r}; valid: {list(aggregator.CATEGORIES)}")
    clients.audit_log(viewer, "metrics.read", category)
    return result
