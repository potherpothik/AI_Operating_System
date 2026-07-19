import datetime
from sqlalchemy.orm import Session

from planning.capability_registry.models import CapabilityRegistryEntry


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def get_active(db: Session, agent_capability: str) -> CapabilityRegistryEntry | None:
    return (
        db.query(CapabilityRegistryEntry)
        .filter(CapabilityRegistryEntry.agent_capability == agent_capability, CapabilityRegistryEntry.status == "active")
        .order_by(CapabilityRegistryEntry.version.desc())
        .first()
    )


def get(db: Session, entry_id: str) -> CapabilityRegistryEntry | None:
    return db.query(CapabilityRegistryEntry).filter(CapabilityRegistryEntry.id == entry_id).first()


def scope_matches(entry: CapabilityRegistryEntry, allowed_actions: list, forbidden_actions: list,
                   requires_approval: list, classification_ceiling: str) -> bool:
    return (
        sorted(entry.allowed_actions) == sorted(allowed_actions)
        and sorted(entry.forbidden_actions) == sorted(forbidden_actions)
        and sorted(entry.requires_approval) == sorted(requires_approval)
        and entry.classification_ceiling == classification_ceiling
    )


def create_active(db: Session, agent_capability: str, allowed_actions: list, forbidden_actions: list,
                   requires_approval: list, classification_ceiling: str, version: str = "1") -> CapabilityRegistryEntry:
    entry = CapabilityRegistryEntry(
        agent_capability=agent_capability, version=version, allowed_actions=allowed_actions,
        forbidden_actions=forbidden_actions, requires_approval=requires_approval,
        classification_ceiling=classification_ceiling, status="active",
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def create_pending(db: Session, agent_capability: str, allowed_actions: list, forbidden_actions: list,
                    requires_approval: list, classification_ceiling: str, version: str, approval_id: str) -> CapabilityRegistryEntry:
    entry = CapabilityRegistryEntry(
        agent_capability=agent_capability, version=version, allowed_actions=allowed_actions,
        forbidden_actions=forbidden_actions, requires_approval=requires_approval,
        classification_ceiling=classification_ceiling, status="pending_approval", approval_id=approval_id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def activate(db: Session, entry_id: str) -> CapabilityRegistryEntry | None:
    entry = get(db, entry_id)
    if not entry:
        return None
    # The version this supersedes stops being active — only one active
    # version per agent_capability at a time.
    previous = get_active(db, entry.agent_capability)
    if previous and previous.id != entry.id:
        previous.status = "superseded"
    entry.status = "active"
    db.commit()
    db.refresh(entry)
    return entry


def reject(db: Session, entry_id: str) -> CapabilityRegistryEntry | None:
    entry = get(db, entry_id)
    if not entry:
        return None
    entry.status = "rejected"
    db.commit()
    db.refresh(entry)
    return entry


def deprecate_pending(db: Session, agent_capability: str, approval_id: str) -> CapabilityRegistryEntry | None:
    active = get_active(db, agent_capability)
    if not active:
        return None
    active.approval_id = approval_id
    # Held in "active" status until the approval resolves — deprecation
    # only actually takes effect via finalize_deprecation, mirroring the
    # register-then-approve pattern rather than deprecating optimistically.
    return active


def finalize_deprecation(db: Session, entry_id: str) -> CapabilityRegistryEntry | None:
    entry = get(db, entry_id)
    if not entry:
        return None
    entry.status = "deprecated"
    entry.deprecated_at = _now()
    db.commit()
    db.refresh(entry)
    return entry


def list_all(db: Session, action_type: str = None, classification_ceiling: str = None, status: str = None) -> list[CapabilityRegistryEntry]:
    q = db.query(CapabilityRegistryEntry)
    if status:
        q = q.filter(CapabilityRegistryEntry.status == status)
    rows = q.order_by(CapabilityRegistryEntry.agent_capability.asc(), CapabilityRegistryEntry.version.desc()).all()
    if action_type:
        rows = [r for r in rows if action_type in (r.allowed_actions or [])]
    if classification_ceiling:
        rows = [r for r in rows if r.classification_ceiling == classification_ceiling]
    return rows
