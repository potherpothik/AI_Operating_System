from agents import clients


class CapabilityRegistryUnavailable(Exception):
    pass


def fetch_capability_roster() -> list:
    """
    Raises rather than returning a fallback — Planner must fail closed if
    the registry is unreachable rather than reasoning against a stale or
    empty guess (Phase 8 doc, Planner failure handling: "if the
    Capability Registry itself is unreachable, Planner fails closed — no
    plan is produced — rather than routing against a stale cached
    registry").
    """
    try:
        return clients.fetch_capability_roster()
    except Exception as e:  # noqa: BLE001
        raise CapabilityRegistryUnavailable(str(e))


def format_roster_for_context(roster: list, exclude: str = "planner") -> str:
    lines = []
    for cap in roster:
        if cap["agent_capability"] == exclude:
            continue
        lines.append(
            f"- {cap['agent_capability']}: allowed_actions={cap['allowed_actions']}, "
            f"classification_ceiling={cap['classification_ceiling']}"
        )
    if not lines:
        return "(no other capabilities are currently registered)"
    return "\n".join(lines)


def augment_task_description(task_description: str) -> str:
    roster = fetch_capability_roster()  # propagates CapabilityRegistryUnavailable — caller fails closed
    roster_text = format_roster_for_context(roster)
    return f"{task_description}\n\n[System: currently registered agent capabilities —\n{roster_text}\n]"
