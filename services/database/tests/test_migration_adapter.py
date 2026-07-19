import ast
import pytest

from database.database_connector.migration_adapter import create_migration, MigrationNotConfigured, UnknownPlatform
from database.database_connector.migration_adapter import django as django_adapter
from database.database_connector.migration_adapter import odoo as odoo_adapter


def test_unknown_platform_raises():
    with pytest.raises(UnknownPlatform):
        create_migration("not_a_real_platform", "task-1", "desc")


def test_django_not_configured_without_env_var(monkeypatch):
    monkeypatch.delenv("DJANGO_PROJECT_PATH", raising=False)
    with pytest.raises(MigrationNotConfigured):
        django_adapter.create_migration("task-1", "Add a discount_pct column")


def test_odoo_not_configured_without_env_var(monkeypatch):
    monkeypatch.delenv("ODOO_MODULES_PATH", raising=False)
    with pytest.raises(MigrationNotConfigured):
        odoo_adapter.create_migration("task-1", "Add a discount_pct column")


def test_django_generates_real_syntactically_valid_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DJANGO_PROJECT_PATH", str(tmp_path))
    result = django_adapter.create_migration("task-42", "Add a discount_pct column to sale_order")
    assert result["status"] == "generated"

    generated_path = tmp_path / result["migration_ref"].split("/")[-1]
    assert generated_path.exists()
    content = generated_path.read_text()
    ast.parse(content)  # genuinely valid Python, not just a string that looks right
    assert "task-42" in content
    assert "discount_pct" in content
    assert "class Migration" in content


def test_odoo_generates_real_syntactically_valid_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ODOO_MODULES_PATH", str(tmp_path))
    result = odoo_adapter.create_migration("task-43", "Backfill missing partner emails")
    assert result["status"] == "generated"

    generated_path = tmp_path / result["migration_ref"].split("/")[-1]
    assert generated_path.exists()
    content = generated_path.read_text()
    ast.parse(content)
    assert "task-43" in content
    assert "def migrate(cr, version)" in content


def test_django_rejects_unsafe_task_id_for_filename(tmp_path, monkeypatch):
    monkeypatch.setenv("DJANGO_PROJECT_PATH", str(tmp_path))
    with pytest.raises(MigrationNotConfigured):
        django_adapter.create_migration("../../etc/passwd", "desc")


def test_create_migration_dispatches_to_configured_django_adapter(tmp_path, monkeypatch):
    monkeypatch.setenv("DJANGO_PROJECT_PATH", str(tmp_path))
    result = create_migration("django", "task-44", "Some real change")
    assert result["status"] == "generated"
