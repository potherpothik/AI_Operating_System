from database.database_connector import scoping


def test_unlisted_column_defaults_to_internal():
    assert scoping.column_classification("demo_erp", "sale_order", "amount_total") == "internal"


def test_confidential_column_declared_explicitly():
    assert scoping.column_classification("demo_erp", "res_partner", "email") == "confidential"


def test_unrecognized_target_defaults_everything_internal():
    assert scoping.column_classification("nonexistent_target", "whatever", "col") == "internal"


def test_filter_columns_with_internal_ceiling_excludes_confidential():
    allowed, denied = scoping.filter_columns("demo_erp", "res_partner", ["id", "name", "email"], "internal")
    assert "email" in denied
    assert "id" in allowed and "name" in allowed


def test_filter_columns_with_confidential_ceiling_includes_everything():
    allowed, denied = scoping.filter_columns("demo_erp", "res_partner", ["id", "name", "email"], "confidential")
    assert denied == []
    assert set(allowed) == {"id", "name", "email"}


def test_filter_columns_with_public_ceiling_excludes_internal_too():
    allowed, denied = scoping.filter_columns("demo_erp", "sale_order", ["id", "amount_total"], "public")
    assert denied == ["id", "amount_total"]
    assert allowed == []


def test_unknown_tier_treated_as_most_restrictive():
    assert scoping.tier_index("not_a_real_tier") == scoping.tier_index("confidential")
