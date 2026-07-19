from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from platform_spine.db import get_db
from platform_spine.models import ConfigOverride
from platform_spine.config_manager.loader import ConfigLoader

router = APIRouter(prefix="/config", tags=["config"])
_loader = ConfigLoader()

# Keys that touch security-relevant behavior. Changes to these are recorded
# as requiring approval rather than applied immediately — actually acting
# on that flag (routing through Security Layer + Human Approval Layer,
# Phase 1) is the caller's responsibility once Phase 5+ exists to call it;
# this phase's job is making sure the flag is set correctly and honored
# by get_config, not skipped.
SECURITY_TAGGED_KEYS = {"external_model_allowed", "classification_default"}


class OverrideRequest(BaseModel):
    service: str
    key: str
    value: str
    set_by: str


@router.get("/{service}")
def get_config(service: str, db: Session = Depends(get_db)):
    resolved = _loader.resolve(service)
    overrides = db.query(ConfigOverride).filter(ConfigOverride.service == service).all()
    for o in overrides:
        # Only apply overrides that don't require approval. A pending
        # security-tagged override is visible via /config/override's
        # response and audit trail, but never silently takes effect here.
        if not o.requires_approval:
            resolved[o.key] = o.value
    return resolved


@router.post("/reload")
def reload_config():
    _loader.reload()
    return {"reloaded": True}


@router.post("/override")
def set_override(req: OverrideRequest, db: Session = Depends(get_db)):
    requires_approval = req.key in SECURITY_TAGGED_KEYS
    override = ConfigOverride(
        service=req.service,
        key=req.key,
        value=req.value,
        set_by=req.set_by,
        requires_approval=requires_approval,
    )
    db.add(override)
    db.commit()
    if requires_approval:
        return {
            "status": "pending_approval",
            "note": "security-tagged key — route through Human Approval Layer before this applies",
        }
    return {"status": "applied"}


@router.get("/schema/{service}")
def schema_for_service(service: str):
    return {"service": service, "known_keys": list(_loader.resolve(service).keys())}
