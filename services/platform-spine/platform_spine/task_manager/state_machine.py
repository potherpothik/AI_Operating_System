VALID_TRANSITIONS = {
    None: {"queued"},  # initial creation
    "queued": {"planning", "in_progress", "needs_clarification"},
    "planning": {"in_progress", "needs_clarification", "failed"},
    "in_progress": {"review", "done", "failed"},
    "review": {"done", "in_progress", "failed"},
    "needs_clarification": {"queued"},
    "done": set(),    # terminal
    "failed": set(),  # terminal
}


class InvalidTransition(Exception):
    pass


def validate_transition(from_status, to_status):
    allowed = VALID_TRANSITIONS.get(from_status, set())
    if to_status not in allowed:
        raise InvalidTransition(f"cannot transition from {from_status!r} to {to_status!r}")
