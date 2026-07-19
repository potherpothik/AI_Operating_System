from database.database_connector.migration_adapter.exceptions import MigrationNotConfigured, UnknownPlatform
from database.database_connector.migration_adapter import django as django_adapter
from database.database_connector.migration_adapter import odoo as odoo_adapter

_ADAPTERS = {"django": django_adapter, "odoo": odoo_adapter}


def create_migration(target_platform: str, task_id: str, description: str) -> dict:
    """
    Routes DDL through the underlying platform's own migration tooling —
    never a raw ALTER/CREATE/DROP from an agent (Phase 7 doc, explicit
    out-of-scope note: "no direct DDL execution path outside the
    underlying platforms' own migration tooling, by design, not a gap").
    """
    adapter = _ADAPTERS.get(target_platform)
    if not adapter:
        raise UnknownPlatform(f"no migration adapter for platform {target_platform!r}")
    return adapter.create_migration(task_id, description)
