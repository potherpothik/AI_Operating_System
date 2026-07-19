from assembly.clients import memory_query, vector_query

# Memory types worth checking for task-relevant context. knowledge_cache
# is deliberately excluded here — it's queried via vector_query below
# instead, since it's vector-backed (Phase 3's design).
_RELEVANT_MEMORY_TYPES = ["decision_history", "business_memory", "project_memory", "architecture_history"]


def _dedupe(candidates: list[dict]) -> list[dict]:
    """Simple substring-containment dedup — good enough to catch the same
    fact surfaced by both a memory record and a vector chunk."""
    kept = []
    kept_texts = []
    for c in candidates:
        text = c["text"]
        if any(text in seen or seen in text for seen in kept_texts):
            continue
        kept.append(c)
        kept_texts.append(text)
    return kept


def gather_candidates(namespace: str, task_description: str, ceiling: str) -> list[dict]:
    candidates = []

    for memory_type in _RELEVANT_MEMORY_TYPES:
        hits = memory_query(memory_type, namespace, task_description, requester_ceiling=ceiling, limit=5)
        for hit in hits:
            candidates.append(
                {
                    "source_type": "memory",
                    "source_id": hit.get("id", ""),
                    "text": hit.get("value", ""),
                    "provenance": memory_type,
                    "score": 0.5,  # memory hits don't carry a similarity score; mid-priority by default
                }
            )

    vector_hits = vector_query(task_description, namespace, classification_ceiling=ceiling, top_k=5)
    for hit in vector_hits:
        candidates.append(
            {
                "source_type": "vector",
                "source_id": hit.get("source_doc_id", ""),
                "text": hit.get("chunk", ""),
                "provenance": hit.get("source", ""),
                "score": hit.get("score", 0.0),
            }
        )

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return _dedupe(candidates)
