import json
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from knowledge.memory_manager.models import MemoryRecord
from knowledge.memory_manager.retention import policy_for
from knowledge import security_client, approval_client

_TIERS = ["public", "internal", "confidential"]


def _within_ceiling(classification: str, ceiling: str) -> bool:
    c = classification if classification in _TIERS else "confidential"
    ceil = ceiling if ceiling in _TIERS else "public"
    return _TIERS.index(c) <= _TIERS.index(ceil)


def write(
    db: Session,
    memory_type: str,
    namespace: str,
    key: str,
    value,
    actor: str,
    classification_hint: str = "internal",
) -> tuple[MemoryRecord, dict]:
    policy = policy_for(memory_type)  # raises ValueError for an unknown type — caller's problem to fix, not silently ignored

    value_str = value if isinstance(value, str) else json.dumps(value)
    classification_result = security_client.classify(value_str, classification_hint)
    classification = classification_result["classification"]

    ttl_expires_at = None
    if policy["ttl_minutes"] is not None:
        ttl_expires_at = datetime.now(timezone.utc) + timedelta(minutes=policy["ttl_minutes"])

    if policy["requires_approval_to_write"]:
        approval = approval_client.request_approval(
            action=f"memory.write.{memory_type}", requested_by=actor, risk_tier="medium", payload_ref=key
        )
        record = MemoryRecord(
            memory_type=memory_type,
            namespace=namespace,
            key=key,
            value=value_str,
            classification=classification,
            created_by=actor,
            ttl_expires_at=ttl_expires_at,
            status="pending_approval" if approval.get("id") else "rejected",
            approval_id=approval.get("id"),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record, {"status": record.status, "approval_id": approval.get("id")}

    prior = None
    if policy["versioned"]:
        prior = (
            db.query(MemoryRecord)
            .filter(
                MemoryRecord.memory_type == memory_type,
                MemoryRecord.namespace == namespace,
                MemoryRecord.key == key,
                MemoryRecord.status == "active",
                MemoryRecord.superseded_by.is_(None),
            )
            .first()
        )

    record = MemoryRecord(
        memory_type=memory_type,
        namespace=namespace,
        key=key,
        value=value_str,
        classification=classification,
        created_by=actor,
        ttl_expires_at=ttl_expires_at,
        status="active",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    if prior:
        prior.superseded_by = record.id
        db.commit()

    return record, {"status": "active"}


def reconcile_pending_approvals(db: Session, memory_type: str = None) -> list[MemoryRecord]:
    """Checks Phase 1 for a decision on any pending business_memory-style writes and applies it."""
    q = db.query(MemoryRecord).filter(MemoryRecord.status == "pending_approval")
    if memory_type:
        q = q.filter(MemoryRecord.memory_type == memory_type)

    updated = []
    for record in q.all():
        if not record.approval_id:
            continue
        result = approval_client.get_status(record.approval_id)
        if result.get("status") == "approved":
            record.status = "active"
            updated.append(record)
        elif result.get("status") in ("rejected", "expired"):
            record.status = "rejected"
            updated.append(record)
    db.commit()
    return updated


def expire_stale(db: Session, memory_type: str = None) -> int:
    """
    Compares in Python rather than at the SQL level — a naive-vs-aware
    datetime mismatch at the SQL layer is exactly the class of bug that
    corrupted timestamps in earlier phases; normalizing here avoids
    relying on how a given backend serializes the comparison.
    """
    q = db.query(MemoryRecord).filter(MemoryRecord.status == "active", MemoryRecord.ttl_expires_at.isnot(None))
    if memory_type:
        q = q.filter(MemoryRecord.memory_type == memory_type)

    now = datetime.now(timezone.utc)
    expired = []
    for r in q.all():
        expires_at = r.ttl_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at.astimezone(timezone.utc) < now:
            r.status = "expired"
            expired.append(r)
    db.commit()
    return len(expired)


def read(db: Session, memory_type: str, namespace: str, key: str, requester_ceiling: str = "confidential"):
    expire_stale(db, memory_type)
    record = (
        db.query(MemoryRecord)
        .filter(
            MemoryRecord.memory_type == memory_type,
            MemoryRecord.namespace == namespace,
            MemoryRecord.key == key,
            MemoryRecord.status == "active",
            MemoryRecord.superseded_by.is_(None),
        )
        .order_by(MemoryRecord.created_at.desc())
        .first()
    )
    if not record:
        return None
    # Classification is enforced at READ time too, not only at write time —
    # a caller without clearance gets nothing back, regardless of what it asks for.
    if not _within_ceiling(record.classification, requester_ceiling):
        return None
    return record


def query_text(db: Session, memory_type: str, namespace: str, text: str, requester_ceiling: str = "confidential", limit: int = 20):
    """Simple substring search over stored values — not semantic. knowledge_cache's
    real semantic query goes through Vector Search instead (see api.py)."""
    expire_stale(db, memory_type)
    rows = (
        db.query(MemoryRecord)
        .filter(
            MemoryRecord.memory_type == memory_type,
            MemoryRecord.namespace == namespace,
            MemoryRecord.status == "active",
            MemoryRecord.superseded_by.is_(None),
            MemoryRecord.value.contains(text),
        )
        .order_by(MemoryRecord.created_at.desc())
        .limit(limit)
        .all()
    )
    return [r for r in rows if _within_ceiling(r.classification, requester_ceiling)]


def delete(db: Session, memory_type: str, record_id: str) -> tuple[bool, str]:
    policy = policy_for(memory_type)
    if not policy["deletable"]:
        return False, f"{memory_type} is not deletable — only superseded, per its retention policy"
    record = db.query(MemoryRecord).filter(MemoryRecord.id == record_id, MemoryRecord.memory_type == memory_type).first()
    if not record:
        return False, "not found"
    db.delete(record)
    db.commit()
    return True, "deleted"
