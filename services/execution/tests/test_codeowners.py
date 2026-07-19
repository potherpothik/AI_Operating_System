from execution.git_manager import codeowners


def test_default_owner_for_unmatched_path():
    assert codeowners.owner_for("README.md") == "@human_admin"


def test_specific_pattern_overrides_default():
    assert codeowners.owner_for("addons/odoo/sale/models.py") == "@odoo-team"


def test_owners_for_files_dedupes():
    owners = codeowners.owners_for_files(["addons/odoo/a.py", "addons/odoo/b.py", "README.md"])
    assert owners == {"@odoo-team", "@human_admin"}
