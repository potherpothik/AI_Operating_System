from control_ui import clients


def build(conversation_id: str, token: str) -> dict:
    """
    Merges every real task (turn) in a conversation with that task's own
    real event history — best-effort per source, same `partial: true`
    pattern Metrics Dashboard (Phase 13) already uses when a peer call
    fails, rather than a single all-or-nothing 500.
    """
    errors = {}
    try:
        tasks = clients.list_tasks_for_conversation(conversation_id, token)
    except Exception as e:  # noqa: BLE001
        tasks = []
        errors["tasks"] = str(e)

    turns = []
    for task in tasks:
        try:
            events = clients.get_task_events(task["id"], token)
        except Exception as e:  # noqa: BLE001
            events = []
            errors[f"events:{task['id']}"] = str(e)
        turns.append({"task": task, "events": events})

    turns.sort(key=lambda t: t["task"]["created_at"])
    return {"conversation_id": conversation_id, "turns": turns, "partial": bool(errors), "errors": errors}
