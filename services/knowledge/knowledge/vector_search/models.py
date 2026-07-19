import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text, Integer

from knowledge.db import Base, IS_POSTGRES
from knowledge.vector_search.embedding import get_default_embedding_model

_DEFAULT_DIM = get_default_embedding_model().dim

if IS_POSTGRES:
    from pgvector.sqlalchemy import Vector

    _EmbeddingColumnType = Vector(_DEFAULT_DIM)
else:
    # SQLite has no vector type — embeddings are stored as JSON-encoded
    # text and compared with Python-computed cosine similarity (index.py).
    # This is a linear scan, fine for correctness testing and small
    # datasets, not a claim of ANN-search performance at scale — that's
    # what the real pgvector path above is for.
    _EmbeddingColumnType = Text


def _uuid() -> str:
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


class Document(Base):
    __tablename__ = "document"

    id = Column(String, primary_key=True, default=_uuid)
    source = Column(String, nullable=False)
    doc_type = Column(String, default="generic")
    project_id = Column(String, nullable=False, index=True)
    classification = Column(String, default="internal")
    version = Column(String, default="1")
    ingested_at = Column(DateTime(timezone=True), default=_now)


class Chunk(Base):
    __tablename__ = "chunk"

    id = Column(String, primary_key=True, default=_uuid)
    document_id = Column(String, nullable=False, index=True)
    content = Column(Text, nullable=False)
    embedding = Column(_EmbeddingColumnType, nullable=False)
    chunk_index = Column(Integer, default=0)
