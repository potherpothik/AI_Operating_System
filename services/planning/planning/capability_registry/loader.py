from sqlalchemy.orm import Session

from planning import clients
from planning.capability_registry import store


def sync_from_agents(db: Session, actor: str = "planner") -> dict:
    """
    Aggregates every agent's capability.yaml (introduced per-agent since
    Phase 5) into this registry's own versioned, queryable index — the
    agents service's GET /capabilities is the live source of truth,
    never a copy this loader could let drift.

    A capability seen for the first time is auto-registered active (it's
    just reflecting an agent that's already shipped and code-reviewed).
    A capability whose scope actually changed from its current active
    version creates a new PENDING version and requires real governance
    approval before it takes effect — the security-relevant event the
    Phase 8 doc calls out. An unchanged capability is a no-op.
    """
    roster = clients.fetch_agent_capabilities()  # raises on failure — sync never partially applies against a broken source
    results = {"registered_new": [], "pending_scope_change": [], "unchanged": []}

    for cap in roster:
        agent_capability = cap["agent_capability"]
        active = store.get_active(db, agent_capability)

        if not active:
            decision = clients.authorize(actor, "capability.register_new", agent_capability)
            if decision["decision"] != "allow":
                clients.audit_log(actor, "capability.register_new", agent_capability, decision="deny", reason=decision.get("reason", ""))
                continue
            store.create_active(
                db, agent_capability, cap["allowed_actions"], cap["forbidden_actions"],
                cap["requires_approval"], cap["classification_ceiling"], version="1",
            )
            clients.audit_log(actor, "capability.register_new", agent_capability, decision="allow", reason="first sync")
            results["registered_new"].append(agent_capability)
            continue

        if store.scope_matches(active, cap["allowed_actions"], cap["forbidden_actions"], cap["requires_approval"], cap["classification_ceiling"]):
            results["unchanged"].append(agent_capability)
            continue

        next_version = str(int(active.version) + 1) if active.version.isdigit() else "2"
        approval = clients.request_approval(
            action=f"capability.change_scope.{agent_capability}", requested_by=actor,
            risk_tier="medium", payload_ref=agent_capability,
        )
        store.create_pending(
            db, agent_capability, cap["allowed_actions"], cap["forbidden_actions"],
            cap["requires_approval"], cap["classification_ceiling"], next_version, approval.get("id"),
        )
        results["pending_scope_change"].append(agent_capability)

    return results


def reconcile_pending(db: Session) -> list:
    """Mirrors Phase 4's template reconcile-approvals pattern exactly."""
    from planning.capability_registry.models import CapabilityRegistryEntry

    updated = []
    pending = db.query(CapabilityRegistryEntry).filter(CapabilityRegistryEntry.status == "pending_approval").all()
    for entry in pending:
        if not entry.approval_id:
            continue
        result = clients.get_approval_status(entry.approval_id)
        if result.get("status") == "approved":
            store.activate(db, entry.id)
            updated.append({"id": entry.id, "agent_capability": entry.agent_capability, "status": "active"})
        elif result.get("status") in ("rejected", "expired"):
            store.reject(db, entry.id)
            updated.append({"id": entry.id, "agent_capability": entry.agent_capability, "status": "rejected"})
    return updated
