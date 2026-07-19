import json
import math
from sqlalchemy.orm import Session

from knowledge.db import IS_POSTGRES
from knowledge.vector_search.models import Document, Chunk
from knowledge.vector_search.chunking import chunk_text
from knowledge.vector_search.embedding import get_default_embedding_model

_model = get_default_embedding_model()
_TIERS = ["public", "internal", "confidential"]


def _within_ceiling(classification: str, ceiling: str) -> bool:
    c = classification if classification in _TIERS else "confidential"
    ceil = ceiling if ceiling in _TIERS else "public"
    return _TIERS.index(c) <= _TIERS.index(ceil)


def _cosine_similarity(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _store_embedding(vec: list) -> object:
    return vec if IS_POSTGRES else json.dumps(vec)


def ingest(
    db: Session,
    source: str,
    content: str,
    project_id: str,
    doc_type: str = "generic",
    classification: str = "internal",
    version: str = "1",
) -> dict:
    doc = Document(source=source, doc_type=doc_type, project_id=project_id, classification=classification, version=version)
    db.add(doc)
    db.commit()
    db.refresh(doc)

    chunks = chunk_text(content)
    for i, chunk_content in enumerate(chunks):
        vec = _model.embed(chunk_content)
        db.add(Chunk(document_id=doc.id, content=chunk_content, embedding=_store_embedding(vec), chunk_index=i))
    db.commit()

    return {"document_id": doc.id, "chunks_created": len(chunks)}


def query(
    db: Session,
    query_text_str: str,
    namespace: str = None,
    classification_ceiling: str = "confidential",
    doc_type: str = None,
    top_k: int = 5,
) -> list[dict]:
    query_vec = _model.embed(query_text_str)

    # Classification and project filtering happen here, server-side,
    # before any similarity ranking — a caller without clearance for
    # confidential content cannot get confidential chunks back no matter
    # what it asks for. This is not a post-filter the caller could bypass.
    doc_q = db.query(Document)
    if namespace:
        doc_q = doc_q.filter(Document.project_id == namespace)
    if doc_type:
        doc_q = doc_q.filter(Document.doc_type == doc_type)
    allowed_tiers = [t for t in _TIERS if _within_ceiling(t, classification_ceiling)]
    doc_q = doc_q.filter(Document.classification.in_(allowed_tiers))

    allowed_docs = doc_q.all()
    if not allowed_docs:
        return []
    doc_by_id = {d.id: d for d in allowed_docs}
    allowed_doc_ids = list(doc_by_id.keys())

    if IS_POSTGRES:
        distance = Chunk.embedding.cosine_distance(query_vec)
        rows = (
            db.query(Chunk, distance.label("distance"))
            .filter(Chunk.document_id.in_(allowed_doc_ids))
            .order_by(distance.asc())
            .limit(top_k)
            .all()
        )
        results = []
        for chunk, distance_val in rows:
            doc = doc_by_id[chunk.document_id]
            results.append(
                {
                    "chunk": chunk.content,
                    "score": 1 - float(distance_val),
                    "source_doc_id": doc.id,
                    "source": doc.source,
                    "classification": doc.classification,
                }
            )
        return results

    # SQLite fallback: linear scan, Python-computed cosine similarity.
    chunks = db.query(Chunk).filter(Chunk.document_id.in_(allowed_doc_ids)).all()
    scored = [(_cosine_similarity(query_vec, json.loads(c.embedding)), c) for c in chunks]
    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, chunk in scored[:top_k]:
        doc = doc_by_id[chunk.document_id]
        results.append(
            {
                "chunk": chunk.content,
                "score": score,
                "source_doc_id": doc.id,
                "source": doc.source,
                "classification": doc.classification,
            }
        )
    return results


def delete_document(db: Session, document_id: str) -> bool:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        return False
    db.query(Chunk).filter(Chunk.document_id == document_id).delete()
    db.delete(doc)
    db.commit()
    return True


def reindex(db: Session, document_id: str, new_content: str) -> dict:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        return {"error": "not found"}

    db.query(Chunk).filter(Chunk.document_id == document_id).delete()
    db.commit()

    chunks = chunk_text(new_content)
    for i, chunk_content in enumerate(chunks):
        vec = _model.embed(chunk_content)
        db.add(Chunk(document_id=doc.id, content=chunk_content, embedding=_store_embedding(vec), chunk_index=i))

    doc.version = str(int(doc.version) + 1) if doc.version.isdigit() else doc.version + "-r"
    db.commit()
    return {"document_id": doc.id, "chunks_created": len(chunks), "version": doc.version}


def stats(db: Session) -> dict:
    doc_count = db.query(Document).count()
    chunk_count = db.query(Chunk).count()
    by_project = {}
    for doc in db.query(Document).all():
        by_project[doc.project_id] = by_project.get(doc.project_id, 0) + 1
    return {"documents": doc_count, "chunks": chunk_count, "by_project": by_project}
