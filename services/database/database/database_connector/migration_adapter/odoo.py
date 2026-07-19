import os
import re
import time
from pathlib import Path

from database.database_connector.migration_adapter.exceptions import MigrationNotConfigured

_SAFE_TASK_ID = re.compile(r"^[A-Za-z0-9._-]+$")

_TEMPLATE = '''\
"""
Agent-proposed Odoo module upgrade script for task {task_id}.

{description}

Generated as a REVIEW ARTIFACT for Odoo's module upgrade mechanism, not
applied automatically — a human reviews and places this under the target
module's migrations/<version>/ directory before the next module upgrade
(Phase 7 doc: DDL always routed through the platform's own migration
tooling, never a raw ALTER/CREATE/DROP from an agent).
"""


def migrate(cr, version):
    # TODO(human review required): replace with the real migration
    # steps this change should perform. Left empty deliberately — an
    # agent proposing a data-model change drafts the script shell and
    # description, a human fills in and reviews the real steps.
    pass
'''


def create_migration(task_id: str, description: str) -> dict:
    """
    Same honesty posture as the Django adapter: no live Odoo module tree
    exists in this environment, so this reports not_configured unless
    ODOO_MODULES_PATH points at a real directory. When configured, writes
    a genuinely syntax-checked (ast.parse) Python migration script.
    """
    modules_path = os.environ.get("ODOO_MODULES_PATH")
    if not modules_path or not Path(modules_path).is_dir():
        raise MigrationNotConfigured("ODOO_MODULES_PATH not set or not a real directory — no live Odoo module tree to target")

    if not task_id or not _SAFE_TASK_ID.match(task_id):
        raise MigrationNotConfigured(f"task_id {task_id!r} unsafe for a filename")

    filename = f"{int(time.time())}_agent_proposed_{task_id}.py"
    file_path = Path(modules_path) / filename
    content = _TEMPLATE.format(task_id=task_id, description=description.replace('"""', "'''"))

    import ast
    ast.parse(content)

    file_path.write_text(content)
    return {"status": "generated", "migration_ref": str(file_path)}
