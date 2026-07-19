import datetime
from sqlalchemy.orm import Session

from extensibility.plugin_system.models import Plugin

# "A plugin causing runtime errors past a threshold is auto-disabled,
# not left running degraded" (doc, Plugin System failure handling).
ERROR_THRESHOLD = 5


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def create_plugin(db: Session, name: str, version: str, capability_yaml: str, template_md: str,
                   expected_output_schema: dict, declared_capabilities: list, required_permissions: list,
                   installed_by: str, approval_id: str) -> Plugin:
    plugin = Plugin(
        name=name, version=version, capability_yaml=capability_yaml, template_md=template_md,
        expected_output_schema=expected_output_schema, declared_capabilities=declared_capabilities or [],
        required_permissions=required_permissions or [], installed_by=installed_by, approval_id=approval_id,
    )
    db.add(plugin)
    db.commit()
    db.refresh(plugin)
    return plugin


def get_plugin(db: Session, plugin_id: str) -> Plugin | None:
    return db.query(Plugin).filter(Plugin.id == plugin_id).first()


def get_plugin_by_name(db: Session, name: str) -> Plugin | None:
    return db.query(Plugin).filter(Plugin.name == name).first()


def list_plugins(db: Session) -> list[Plugin]:
    return db.query(Plugin).order_by(Plugin.installed_at.desc()).all()


def activate_plugin(db: Session, plugin: Plugin) -> Plugin:
    plugin.status = "active"
    plugin.decided_at = _now()
    db.commit()
    db.refresh(plugin)
    return plugin


def reject_plugin(db: Session, plugin: Plugin) -> Plugin:
    plugin.status = "rejected"
    plugin.decided_at = _now()
    db.commit()
    db.refresh(plugin)
    return plugin


def disable_plugin(db: Session, plugin: Plugin) -> Plugin:
    plugin.status = "disabled"
    db.commit()
    db.refresh(plugin)
    return plugin


def record_error(db: Session, plugin: Plugin) -> tuple[Plugin, bool]:
    """Returns (plugin, auto_disabled). Increments error_count and
    disables the plugin the moment it crosses ERROR_THRESHOLD — never
    left running degraded past that point."""
    plugin.error_count += 1
    auto_disabled = False
    if plugin.error_count >= ERROR_THRESHOLD and plugin.status == "active":
        plugin.status = "disabled"
        auto_disabled = True
    db.commit()
    db.refresh(plugin)
    return plugin, auto_disabled
