from sqlalchemy.orm import Session

from assembly.context_builder.models import ContextPackage, ContextItem, PinnedFact
from assembly.context_builder.classification import ceiling_for_model
from assembly.context_builder.retriever import gather_candidates
from assembly.context_builder.budget import fit_to_budget, word_count
from assembly.clients import audit_log

DEFAULT_BUDGET_WORDS = 1500


def build(
    db: Session,
    task_id: str,
    task_description: str,
    agent_capability: str,
    target_model: str,
    namespace: str,
    budget_words: int = DEFAULT_BUDGET_WORDS,
) -> ContextPackage:
    ceiling_info = ceiling_for_model(target_model)
    ceiling = ceiling_info["ceiling"]

    pinned = (
        db.query(PinnedFact)
        .filter(PinnedFact.namespace == namespace)
        .filter((PinnedFact.agent_capability == agent_capability) | (PinnedFact.agent_capability.is_(None)))
        .all()
    )
    pinned_candidates = [
        {"source_type": "pinned", "source_id": p.id, "text": p.content, "provenance": "human-pinned", "score": float("inf")}
        for p in pinned
    ]

    retrieved = gather_candidates(namespace, task_description, ceiling)

    # Pinned facts sort first regardless of retrieval score — a human
    # explicitly said "always include this", so budget truncation should
    # drop lower-relevance retrieved content before ever dropping a pin.
    all_candidates = sorted(pinned_candidates + retrieved, key=lambda c: c["score"], reverse=True)

    included, used, truncated = fit_to_budget(all_candidates, budget_words)

    package = ContextPackage(
        task_id=task_id,
        agent_capability=agent_capability,
        target_model=target_model,
        classification_ceiling=ceiling,
        budget_used=used,
        budget_total=budget_words,
        partial=truncated,
    )
    db.add(package)
    db.commit()
    db.refresh(package)

    for item in included:
        db.add(
            ContextItem(
                context_package_id=package.id,
                source_type=item["source_type"],
                source_id=item.get("source_id", ""),
                content=item["text"],
                provenance=item.get("provenance", ""),
                included_reason="pinned" if item["source_type"] == "pinned" else "top-k relevance",
            )
        )
    db.commit()

    # Log a REFERENCE to the central audit trail, not the full content —
    # the full package lives in context_package/context_item, with its
    # own retention rule (Phase 4 design doc). Best-effort: a failed
    # audit call doesn't block context assembly, but it also doesn't
    # pretend to have succeeded — see the honesty note in the README.
    audit_log(
        actor_id="context_builder",
        action="context.build",
        resource=package.id,
        reason=f"task={task_id} capability={agent_capability} ceiling={ceiling} partial={truncated}",
        correlation_id=task_id,
    )

    return package


def get_package(db: Session, context_id: str):
    package = db.query(ContextPackage).filter(ContextPackage.id == context_id).first()
    if not package:
        return None
    items = db.query(ContextItem).filter(ContextItem.context_package_id == context_id).all()
    return package, items


def pin_fact(db: Session, namespace: str, content: str, pinned_by: str, agent_capability: str = None) -> PinnedFact:
    fact = PinnedFact(namespace=namespace, agent_capability=agent_capability, content=content, pinned_by=pinned_by)
    db.add(fact)
    db.commit()
    db.refresh(fact)
    return fact
