from database.database_connector import scoping


def test_unlisted_column_defaults_to_internal():
    assert scoping.column_classification("demo_erp", "sale_order", "amount_total") == "internal"


def test_confidential_column_declared_explicitly():
    assert scoping.column_classification("demo_erp", "res_partner", "email") == "confidential"


def test_unrecognized_target_defaults_everything_internal():
    assert scoping.column_classification("nonexistent_target", "whatever", "col") == "internal"


def test_filter_columns_excludes_pii_tagged_column_regardless_of_ceiling():
    # email is PII-tagged (Phase 15) — filter_columns skips it entirely,
    # at any ceiling, since it's governed exclusively by filter_pii_columns
    # now (see the PII-dimension tests below).
    allowed, denied = scoping.filter_columns("demo_erp", "res_partner", ["id", "name", "email"], "internal")
    assert "email" not in allowed and "email" not in denied
    assert "id" in allowed and "name" in allowed

    allowed, denied = scoping.filter_columns("demo_erp", "res_partner", ["id", "name", "email"], "confidential")
    assert "email" not in allowed and "email" not in denied
    assert set(allowed) == {"id", "name"}


def test_filter_columns_with_public_ceiling_excludes_internal_too():
    allowed, denied = scoping.filter_columns("demo_erp", "sale_order", ["id", "amount_total"], "public")
    assert denied == ["id", "amount_total"]
    assert allowed == []


def test_unknown_tier_treated_as_most_restrictive():
    assert scoping.tier_index("not_a_real_tier") == scoping.tier_index("confidential")


# Phase 15 — PII dimension, orthogonal to the tier scale above.

def test_pii_columns_lists_registered_columns():
    assert scoping.pii_columns("demo_erp", "res_partner") == ["email"]


def test_pii_columns_empty_for_untagged_table():
    assert scoping.pii_columns("demo_erp", "sale_order") == []


def test_pii_columns_empty_for_unrecognized_target():
    assert scoping.pii_columns("nonexistent_target", "res_partner") == []


def test_authorized_capability_recognized():
    assert scoping.capability_authorized_for_pii("demo_erp", "sales_agent") is True


def test_unlisted_capability_not_authorized_for_pii():
    assert scoping.capability_authorized_for_pii("demo_erp", "database_agent") is False


def test_unrecognized_target_never_authorized_for_pii():
    assert scoping.capability_authorized_for_pii("nonexistent_target", "sales_agent") is False


def test_filter_pii_columns_excludes_untagged_field_by_default():
    # Only PII-tagged columns are this function's concern at all — id/name
    # never appear in its output, allowed or denied (filter_columns owns
    # those).
    allowed, denied = scoping.filter_pii_columns("demo_erp", "res_partner", ["id", "name", "email"], pii_fields_requested=[])
    assert denied == ["email"]
    assert allowed == []


def test_filter_pii_columns_includes_explicitly_requested_field():
    allowed, denied = scoping.filter_pii_columns("demo_erp", "res_partner", ["id", "name", "email"], pii_fields_requested=["email"])
    assert denied == []
    assert allowed == ["email"]


def test_filter_pii_columns_ignores_non_pii_columns_entirely():
    # A column with no PII tag never appears in this function's output at
    # all, whether or not it's named in pii_fields_requested — it's
    # simply not this gate's concern.
    allowed, denied = scoping.filter_pii_columns("demo_erp", "sale_order", ["id", "amount_total"], pii_fields_requested=["amount_total"])
    assert allowed == [] and denied == []


def test_pii_gate_is_independent_of_ceiling_not_layered_on_top_of_it():
    """
    The bug this regression test locks in: an earlier version ran the PII
    gate AFTER the ceiling gate, so a capability deliberately kept at a
    LOW ceiling (Sales Agent: internal, never confidential — it has no
    business seeing confidential data in general) could never see an
    explicitly-authorized, explicitly-requested PII field, because the
    ceiling gate silently vetoed it first. Found live via Sales Agent's
    own reasoning-loop test. filter_columns now skips PII-tagged columns
    entirely, so the ceiling never gets a vote on them either way — only
    filter_pii_columns decides, regardless of requester_ceiling.
    """
    ceiling_allowed, ceiling_denied = scoping.filter_columns("demo_erp", "res_partner", ["id", "name", "email"], "internal")
    assert "email" not in ceiling_allowed and "email" not in ceiling_denied  # the ceiling gate has no opinion on it

    pii_allowed, _ = scoping.filter_pii_columns("demo_erp", "res_partner", ["id", "name", "email"], pii_fields_requested=["email"])
    assert pii_allowed == ["email"]  # explicitly requested and PII-authorized is sufficient — a low ceiling doesn't block it
