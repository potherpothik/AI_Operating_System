import datetime
from sqlalchemy.orm import Session

from observability.health_monitor.models import AlertConfig, HealthPollLog


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def create_alert_config(db: Session, metric_or_gap: str, threshold: int, destination_ref: str, created_by: str) -> AlertConfig:
    row = AlertConfig(metric_or_gap=metric_or_gap, threshold=threshold, destination_ref=destination_ref, created_by=created_by)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_alert_configs(db: Session) -> list[AlertConfig]:
    return db.query(AlertConfig).order_by(AlertConfig.created_at.desc()).all()


def record_poll(db: Session, services_down: list, gaps_found: list) -> HealthPollLog:
    row = HealthPollLog(services_down=services_down, gaps_found=gaps_found)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
