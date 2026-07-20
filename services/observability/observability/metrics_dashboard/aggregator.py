import datetime

from observability import clients

CATEGORIES = (
    "task_throughput_latency",
    "reasoning_iterations",
    "approval_queue",
    "tool_execution_volume",
    "classification_distribution",
)


def _parse_ts(value: str) -> datetime.datetime:
    """Same naive-timestamp normalization as health_monitor/checks.py's
    _parse_ts — a SQLite-backed peer drops timezone info on round-trip,
    and every _now() helper in this codebase produces UTC regardless."""
    parsed = datetime.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def task_throughput_latency(since: str = None) -> dict:
    """Task Manager (Phase 2) — count by status, and average completion
    latency (updated_at - created_at) for tasks that reached `done`."""
    tasks = clients.get_tasks()
    cutoff = _parse_ts(since) if since else None

    by_status = {}
    latencies_seconds = []
    for t in tasks:
        if cutoff and _parse_ts(t["created_at"]) < cutoff:
            continue
        by_status[t["status"]] = by_status.get(t["status"], 0) + 1
        if t["status"] == "done":
            duration = (_parse_ts(t["updated_at"]) - _parse_ts(t["created_at"])).total_seconds()
            latencies_seconds.append(duration)

    return {
        "category": "task_throughput_latency", "total": sum(by_status.values()), "by_status": by_status,
        "avg_latency_seconds_for_done": _avg(latencies_seconds), "partial": len(tasks) == 0 and by_status == {},
    }


def reasoning_iterations(since: str = None) -> dict:
    """Reasoning Engine (Phase 5) — iterations used per execution,
    broken down by agent_capability and by terminal status."""
    executions = clients.get_reasoning_executions()
    cutoff = _parse_ts(since) if since else None

    by_capability = {}
    by_status = {}
    iterations = []
    for e in executions:
        if cutoff and _parse_ts(e["created_at"]) < cutoff:
            continue
        by_capability[e["agent_capability"]] = by_capability.get(e["agent_capability"], 0) + 1
        by_status[e["status"]] = by_status.get(e["status"], 0) + 1
        iterations.append(e["iterations_used"])

    return {
        "category": "reasoning_iterations", "total_executions": len(iterations),
        "avg_iterations_used": _avg(iterations), "by_agent_capability": by_capability, "by_status": by_status,
        "partial": len(executions) == 0,
    }


def approval_queue(since: str = None) -> dict:
    """Human Approval Layer (Phase 1) — queue depth (still pending) and
    time-to-decision for requests that were actually decided."""
    all_requests = clients.get_approvals()
    cutoff = _parse_ts(since) if since else None

    pending_count = 0
    decision_times_seconds = []
    for r in all_requests:
        if cutoff and _parse_ts(r["created_at"]) < cutoff:
            continue
        if r["status"] == "pending":
            pending_count += 1
        elif r.get("decided_at"):
            duration = (_parse_ts(r["decided_at"]) - _parse_ts(r["created_at"])).total_seconds()
            decision_times_seconds.append(duration)

    return {
        "category": "approval_queue", "pending_count": pending_count,
        "avg_time_to_decision_seconds": _avg(decision_times_seconds), "decided_count": len(decision_times_seconds),
        "partial": len(all_requests) == 0 and pending_count == 0,
    }


def tool_execution_volume(since: str = None) -> dict:
    """Shell Executor (Phase 6) + Database Connector (Phase 7) — real
    tool-call volume by requesting capability, across both execution
    surfaces every agent actually uses."""
    shell = clients.get_shell_executions()
    db_log = clients.get_db_query_log()
    cutoff = _parse_ts(since) if since else None

    by_capability = {}
    for e in shell:
        if cutoff and _parse_ts(e["created_at"]) < cutoff:
            continue
        cap = e["requesting_capability"]
        by_capability.setdefault(cap, {"shell": 0, "db": 0})
        by_capability[cap]["shell"] += 1
    for row in db_log:
        if cutoff and _parse_ts(row["ts"]) < cutoff:
            continue
        cap = row["capability"]
        by_capability.setdefault(cap, {"shell": 0, "db": 0})
        by_capability[cap]["db"] += 1

    return {
        "category": "tool_execution_volume", "by_capability": by_capability,
        "total_shell": len(shell), "total_db": len(db_log),
        "partial": len(shell) == 0 and len(db_log) == 0,
    }


def classification_distribution() -> dict:
    """Vector Search (Phase 3) / Context Builder — the one category with
    an actual classification dimension on the underlying rows."""
    stats = clients.get_vector_stats()
    by_classification = stats.get("by_classification", {})
    return {
        "category": "classification_distribution", "by_classification": by_classification,
        "total_documents": stats.get("documents", 0), "partial": not stats,
    }


_CATEGORY_FUNCS = {
    "task_throughput_latency": task_throughput_latency,
    "reasoning_iterations": reasoning_iterations,
    "approval_queue": approval_queue,
    "tool_execution_volume": tool_execution_volume,
    "classification_distribution": classification_distribution,
}


def category(name: str, since: str = None) -> dict | None:
    func = _CATEGORY_FUNCS.get(name)
    if not func:
        return None
    return func(since) if name != "classification_distribution" else func()


def overview(since: str = None) -> dict:
    """One number per category — GET /metrics/overview. A category whose
    source was unreachable still returns real zeros with partial=true,
    never blanks the whole response (doc, Metrics Dashboard failure handling)."""
    return {name: category(name, since) for name in CATEGORIES}
