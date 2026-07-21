from sqlalchemy.orm import Session
from platform_spine.models import Conversation


def create(db: Session, title: str, created_by: str) -> Conversation:
    conversation = Conversation(title=title, created_by=created_by)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def get(db: Session, conversation_id: str) -> Conversation | None:
    return db.query(Conversation).filter(Conversation.id == conversation_id).first()


def list_for_actor(db: Session, created_by: str = None, limit: int = 100):
    q = db.query(Conversation).filter(Conversation.archived_at.is_(None))
    if created_by:
        q = q.filter(Conversation.created_by == created_by)
    return q.order_by(Conversation.updated_at.desc()).limit(limit).all()
