"""
One entry per memory type from the Phase 3 design doc. Each rule says:
  - ttl_minutes: None means indefinite: retained until explicitly superseded
    or archived, never auto-expired.
  - deletable: whether a direct delete is allowed at all (decision/architecture
    history are append-only — never deletable, only superseded).
  - versioned: whether writes supersede a prior record rather than overwrite it.
  - requires_approval_to_write: routes through Phase 1's Human Approval Layer
    before a write takes effect.
"""

RETENTION_POLICY = {
    "short_term": {
        "ttl_minutes": 30,
        "deletable": True,
        "versioned": False,
        "requires_approval_to_write": False,
    },
    "working": {
        "ttl_minutes": 240,  # backstop; ideally cleared on task completion once Reasoning Engine (Phase 5) exists
        "deletable": True,
        "versioned": False,
        "requires_approval_to_write": False,
    },
    "long_term": {
        "ttl_minutes": None,
        "deletable": False,
        "versioned": True,
        "requires_approval_to_write": False,
    },
    "project_memory": {
        "ttl_minutes": None,
        "deletable": False,  # archived, not deleted, when a project closes
        "versioned": False,
        "requires_approval_to_write": False,
    },
    "business_memory": {
        "ttl_minutes": None,
        "deletable": False,
        "versioned": True,
        "requires_approval_to_write": True,
    },
    "user_preferences": {
        "ttl_minutes": None,
        "deletable": True,  # user can delete their own — a privacy/erasure requirement
        "versioned": False,
        "requires_approval_to_write": False,
    },
    "decision_history": {
        "ttl_minutes": None,
        "deletable": False,  # append-only, like an ADR — only ever superseded
        "versioned": True,
        "requires_approval_to_write": False,
    },
    "architecture_history": {
        "ttl_minutes": None,
        "deletable": False,
        "versioned": True,
        "requires_approval_to_write": False,
    },
    "conversation_history": {
        "ttl_minutes": 60 * 24 * 90,  # 90 days default, per the design doc's compliance-driven default
        "deletable": True,
        "versioned": False,
        "requires_approval_to_write": False,
    },
    "knowledge_cache": {
        "ttl_minutes": 60 * 24 * 7,  # 7-day backstop; real invalidation is source-change-triggered (Vector Search)
        "deletable": True,
        "versioned": False,
        "requires_approval_to_write": False,
    },
}


def policy_for(memory_type: str) -> dict:
    if memory_type not in RETENTION_POLICY:
        raise ValueError(f"unknown memory type: {memory_type!r}")
    return RETENTION_POLICY[memory_type]
