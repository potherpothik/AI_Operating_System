import datetime
import os

from observability import clients

# "Task Manager's SLA flag" (named in the original phase-13 design
# language) does not exist as a stored field anywhere in Phase 2 — no
# phase ever added one. This threshold is computed staleness instead,
# the honest equivalent, not an assumption that a flag exists.
STUCK_TASK_THRESHOLD_MINUTES = int(os.environ.get("STUCK_TASK_THRESHOLD_MINUTES", "60"))

_NON_TERMINAL_TASK_STATUSES = {"queued", "planning", "in_progress", "review", "needs_clarification"}


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _parse_ts(value: str) -> datetime.datetime:
    """
    A peer service running on SQLite (the zero-setup default every
    service falls back to without an explicit DATABASE_URL) silently
    drops timezone info on round-trip — SQLite has no real TIMESTAMPTZ
    type, confirmed by this exact class of bug in Phase 1's own Postgres
    honesty notes. A naive string back from `isoformat()` here still
    means UTC (every `_now()` helper in this codebase produces UTC), so
    it's normalized rather than left to blow up the very first real
    comparison against an aware `datetime.now(timezone.utc)`.
    """
    parsed = datetime.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def check_governance_reachable() -> bool:
    from observability.registry import service_url
    result = clients.poll_health("governance", service_url("governance"))
    return result["status"] == "up"


def check_stuck_tasks() -> list[dict]:
    """A task in a non-terminal status whose own `updated_at` hasn't
    moved in STUCK_TASK_THRESHOLD_MINUTES — computed, not read from a
    stored flag (see module docstring)."""
    cutoff = _now() - datetime.timedelta(minutes=STUCK_TASK_THRESHOLD_MINUTES)
    stuck = []
    for task in clients.get_tasks():
        if task["status"] not in _NON_TERMINAL_TASK_STATUSES:
            continue
        if _parse_ts(task["updated_at"]) < cutoff:
            stuck.append({"task_id": task["id"], "title": task["title"], "status": task["status"], "updated_at": task["updated_at"]})
    return stuck


def check_stale_erp_knowledge() -> list[dict]:
    """Phase 9's `stale` status, across every target_db that's ever been
    synced — not just one you already know to ask about."""
    return [
        {"target_db": s["target_db"], "synced_at": s["synced_at"]}
        for s in clients.get_erp_snapshots()
        if s["status"] == "stale"
    ]


def check_stuck_reasoning_executions() -> list[dict]:
    """
    Reasoning Engine's loop is synchronous — execute() runs its
    iterations and returns, so there's no "still running" state that
    persists between calls the way a background job would have. The
    honest signal for "stuck past max_iterations" in THIS architecture
    is a completed execution whose failure_reason shows it burned every
    iteration without resolving, not a live in-progress poll.
    """
    stuck = []
    for execution in clients.get_reasoning_executions(status="failed"):
        reason = execution.get("failure_reason") or ""
        if reason.startswith("iteration_limit_exceeded"):
            stuck.append({
                "execution_id": execution["id"], "task_id": execution["task_id"],
                "agent_capability": execution["agent_capability"], "iterations_used": execution["iterations_used"],
                "max_iterations": execution["max_iterations"],
            })
    return stuck
