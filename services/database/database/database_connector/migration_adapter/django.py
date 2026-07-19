import os
import re
import time
from pathlib import Path

from database.database_connector.migration_adapter.exceptions import MigrationNotConfigured

_SAFE_TASK_ID = re.compile(r"^[A-Za-z0-9._-]+$")

_TEMPLATE = '''\
"""
Agent-proposed migration for task {task_id}.

{description}

Generated as a REVIEW ARTIFACT, not applied automatically — a human runs
`manage.py migrate` after reviewing this file, same as any other Django
migration (Phase 7 doc: DDL always routed through the platform's own
migration tooling, never a raw ALTER/CREATE/DROP from an agent).
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = []

    operations = [
        # TODO(human review required): replace with the real operation(s)
        # this migration should perform. Left empty deliberately — an
        # agent proposing schema changes drafts the migration shell and
        # description, a human fills in and reviews the actual operation.
    ]
'''


def create_migration(task_id: str, description: str) -> dict:
    """
    Real deployments would target an actual Django app's migrations/
    directory; this environment has no live Django project, so this
    reports not_configured cleanly (via MigrationNotConfigured) unless
    DJANGO_PROJECT_PATH points at a real, existing directory — same
    honesty pattern as Phase 6's untested GitHubAdapter. When it IS
    configured, this genuinely writes a syntactically valid migration
    file (self-verified with ast.parse, not just assumed).
    """
    project_path = os.environ.get("DJANGO_PROJECT_PATH")
    if not project_path or not Path(project_path).is_dir():
        raise MigrationNotConfigured("DJANGO_PROJECT_PATH not set or not a real directory — no live Django project to target")

    if not task_id or not _SAFE_TASK_ID.match(task_id):
        raise MigrationNotConfigured(f"task_id {task_id!r} unsafe for a filename")

    filename = f"{int(time.time())}_agent_proposed_{task_id}.py"
    file_path = Path(project_path) / filename
    content = _TEMPLATE.format(task_id=task_id, description=description.replace('"""', "'''"))

    import ast
    ast.parse(content)  # fail loudly here rather than write invalid Python to disk

    file_path.write_text(content)
    return {"status": "generated", "migration_ref": str(file_path)}
