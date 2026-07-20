from agents import clients

# Phase 15: Project Management Agent's one genuinely new tool call — the
# same non-terminal shape database_bridge.py/shell_bridge.py already
# established: Reasoning Engine fetches the REAL task state and its real
# transition history from Task Manager (Phase 2) and feeds it back into
# context, rather than trusting the model's guess about "why is this
# task slow."
TOOL_ACTIONS = {"task.read"}


def handle_tool_call(parsed: dict, agent_capability: str, task_id: str, correlation_id: str = None) -> dict:
    action = parsed.get("action")
    target_task_id = (parsed.get("target_task_id") or "").strip()
    if not target_task_id:
        return {"summary": "target_task_id was empty — nothing to look up"}

    if action == "task.read":
        task_result = clients.get_task(target_task_id, correlation_id=correlation_id or "")
        if not task_result.get("ok"):
            return {"summary": f"task lookup failed: {task_result.get('error')}"}

        events_result = clients.get_task_events(target_task_id, correlation_id=correlation_id or "")
        if not events_result.get("ok"):
            task = task_result["task"]
            return {"summary": f"task {target_task_id}: status={task.get('status')}, title={task.get('title')!r} — event history lookup failed: {events_result.get('error')}"}

        task = task_result["task"]
        events = events_result["events"]
        transitions = "; ".join(f"{e['from_status']}->{e['to_status']} at {e['ts']} ({e['detail']})" for e in events)
        return {"summary": f"task {target_task_id}: status={task.get('status')}, title={task.get('title')!r}, {len(events)} event(s): {transitions}"}

    return {"summary": f"unrecognized tool action {action!r}"}
