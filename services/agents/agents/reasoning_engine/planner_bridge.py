import os
import httpx

CAPABILITY_REGISTRY_URL = os.environ.get("CAPABILITY_REGISTRY_URL", "http://localhost:8008")


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
        resp = httpx.get(f"{CAPABILITY_REGISTRY_URL}/capabilities", timeout=10.0)
        resp.raise_for_status()
        return resp.json()["capabilities"]
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
