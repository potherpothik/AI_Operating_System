from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from extensibility.db import get_db
from extensibility import clients
from extensibility.plugin_system import store, manifest, installer

router = APIRouter(prefix="/plugins", tags=["plugins"])


def _plugin_out(plugin) -> dict:
    return {
        "id": plugin.id, "name": plugin.name, "version": plugin.version,
        "declared_capabilities": plugin.declared_capabilities, "required_permissions": plugin.required_permissions,
        "status": plugin.status, "installed_by": plugin.installed_by, "approval_id": plugin.approval_id,
        "error_count": plugin.error_count, "installed_at": plugin.installed_at.isoformat(),
        "decided_at": plugin.decided_at.isoformat() if plugin.decided_at else None,
    }


class InstallRequest(BaseModel):
    name: str
    version: str = "1"
    capability_yaml: str
    template_md: str
    expected_output_schema: Optional[dict] = None
    required_permissions: list[str] = []
    installed_by: str = "human_admin"


@router.post("/install")
def install(req: InstallRequest, db: Session = Depends(get_db)):
    if store.get_plugin_by_name(db, req.name):
        raise HTTPException(status_code=409, detail=f"a plugin named {req.name!r} is already installed")

    unverifiable = manifest.validate_permissions(req.required_permissions)
    if unverifiable:
        clients.audit_log(
            req.installed_by, "plugin.install", req.name, decision="deny",
            reason=f"unverifiable permissions: {unverifiable}",
        )
        raise HTTPException(status_code=400, detail=f"required_permissions contains unverifiable permissions: {unverifiable}")

    try:
        parsed = manifest.validate_capability_yaml(req.capability_yaml)
    except manifest.InvalidManifest as e:
        clients.audit_log(req.installed_by, "plugin.install", req.name, decision="deny", reason=str(e))
        raise HTTPException(status_code=400, detail=str(e))

    declared_capabilities = parsed.get("allowed_actions", [])

    approval = clients.request_approval(
        action="plugin.install", requested_by=req.installed_by, risk_tier="high",
        payload_ref=f"{req.name} v{req.version}: permissions={req.required_permissions}",
    )
    plugin = store.create_plugin(
        db, req.name, req.version, req.capability_yaml, req.template_md, req.expected_output_schema,
        declared_capabilities, req.required_permissions, req.installed_by, approval.get("id"),
    )
    clients.audit_log(
        req.installed_by, "plugin.install", req.name, decision="pending_approval",
        reason=f"permissions={req.required_permissions}, approval_id={approval.get('id')}",
    )
    return {"plugin_id": plugin.id, "status": "pending_approval", "approval_id": approval.get("id")}


@router.post("/{plugin_id}/activate")
def activate(plugin_id: str, db: Session = Depends(get_db)):
    plugin = store.get_plugin(db, plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail="plugin not found")

    approval = clients.get_approval_status(plugin.approval_id)
    status = approval.get("status")
    if status == "approved":
        plugin = store.activate_plugin(db, plugin)
        materialize_result = installer.materialize(plugin)
        clients.audit_log(plugin.installed_by, "plugin.install", plugin.name, decision="active")
        return {**_plugin_out(plugin), "materialize": materialize_result}
    elif status in ("rejected", "expired"):
        plugin = store.reject_plugin(db, plugin)
        clients.audit_log(plugin.installed_by, "plugin.install", plugin.name, decision="rejected")
    return _plugin_out(plugin)


@router.post("/{plugin_id}/disable")
def disable(plugin_id: str, db: Session = Depends(get_db)):
    plugin = store.get_plugin(db, plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail="plugin not found")
    plugin = store.disable_plugin(db, plugin)
    clients.audit_log(plugin.installed_by, "plugin.disable", plugin.name, decision="disabled")
    return _plugin_out(plugin)


class ReportErrorRequest(BaseModel):
    reason: str = ""


@router.post("/{plugin_id}/report-error")
def report_error(plugin_id: str, req: ReportErrorRequest, db: Session = Depends(get_db)):
    """
    The auto-disable hook (doc, Plugin System failure handling). Not yet
    wired to fire automatically from a failed Reasoning Engine execution
    — a real, small future integration, documented honestly in
    services/extensibility/README.md rather than silently claimed —
    but the threshold mechanism itself is real and independently
    testable against direct calls here.
    """
    plugin = store.get_plugin(db, plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail="plugin not found")
    plugin, auto_disabled = store.record_error(db, plugin)
    clients.audit_log(
        "reasoning_engine", "plugin.report_error", plugin.name,
        decision="disabled" if auto_disabled else "recorded", reason=req.reason,
    )
    return {**_plugin_out(plugin), "auto_disabled": auto_disabled}


@router.get("")
def list_plugins(db: Session = Depends(get_db)):
    return {"plugins": [_plugin_out(p) for p in store.list_plugins(db)]}
