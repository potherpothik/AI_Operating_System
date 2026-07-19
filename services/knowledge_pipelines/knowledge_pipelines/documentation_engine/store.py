import datetime
from sqlalchemy.orm import Session

from knowledge_pipelines.documentation_engine.models import DocSource, DocIngestionLog


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def get_or_create_source(db: Session, path_or_url: str, source_type: str, doc_type: str, project_id: str, watch_enabled: bool = False) -> DocSource:
    existing = db.query(DocSource).filter(DocSource.path_or_url == path_or_url, DocSource.project_id == project_id).first()
    if existing:
        return existing
    source = DocSource(
        path_or_url=path_or_url, source_type=source_type, doc_type=doc_type,
        project_id=project_id, watch_enabled=watch_enabled,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def update_source_after_ingest(db: Session, source: DocSource, content_hash: str, document_id: str, status: str) -> DocSource:
    source.content_hash = content_hash
    source.document_id = document_id
    source.last_ingested_at = _now()
    source.last_status = status
    db.commit()
    db.refresh(source)
    return source


def mark_stale(db: Session, source_id: str) -> DocSource | None:
    source = db.query(DocSource).filter(DocSource.id == source_id).first()
    if not source:
        return None
    source.last_status = "stale"
    db.commit()
    db.refresh(source)
    return source


def log_ingestion(db: Session, doc_source_id: str, status: str, document_id: str = None,
                   classification_assigned: str = None, classification_is_default: bool = False,
                   failure_reason: str = None) -> DocIngestionLog:
    log = DocIngestionLog(
        doc_source_id=doc_source_id, document_id=document_id, status=status,
        classification_assigned=classification_assigned, classification_is_default=classification_is_default,
        failure_reason=failure_reason,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def get_source(db: Session, source_id: str) -> DocSource | None:
    return db.query(DocSource).filter(DocSource.id == source_id).first()


def list_sources(db: Session, project_id: str = None) -> list[DocSource]:
    q = db.query(DocSource)
    if project_id:
        q = q.filter(DocSource.project_id == project_id)
    return q.order_by(DocSource.path_or_url.asc()).all()
