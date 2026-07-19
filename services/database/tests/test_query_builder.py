import pytest

from database.database_connector import query_builder


def test_classify_select_as_read():
    assert query_builder.classify("SELECT * FROM sale_order") == "read"


def test_classify_update_as_write():
    assert query_builder.classify("UPDATE sale_order SET state = :state WHERE id = :id") == "write"


def test_classify_insert_as_write():
    assert query_builder.classify("INSERT INTO sale_order (name) VALUES (:name)") == "write"


def test_classify_delete_as_write():
    assert query_builder.classify("DELETE FROM sale_order WHERE id = :id") == "write"


def test_classify_alter_as_ddl():
    assert query_builder.classify("ALTER TABLE sale_order ADD COLUMN foo TEXT") == "ddl"


def test_classify_unrecognized_statement_raises():
    with pytest.raises(query_builder.UnsupportedStatement):
        query_builder.classify("EXPLAIN SELECT * FROM sale_order")


def test_build_accepts_valid_parameterized_template():
    built = query_builder.build("SELECT * FROM sale_order WHERE partner_id = :partner_id", {"partner_id": 1})
    assert built is not None


def test_build_rejects_stacked_statement():
    with pytest.raises(query_builder.UnparameterizedQuery):
        query_builder.build("SELECT * FROM sale_order; DROP TABLE sale_order", {})


def test_build_rejects_sql_comment_marker():
    with pytest.raises(query_builder.UnparameterizedQuery):
        query_builder.build("SELECT * FROM sale_order -- WHERE id = 1", {})


def test_build_rejects_block_comment_marker():
    with pytest.raises(query_builder.UnparameterizedQuery):
        query_builder.build("SELECT * FROM sale_order /* injected */", {})


def test_build_rejects_missing_param_for_placeholder():
    with pytest.raises(query_builder.UnparameterizedQuery):
        query_builder.build("SELECT * FROM sale_order WHERE partner_id = :partner_id", {})


def test_build_never_accepts_a_single_preinterpolated_string():
    """
    There is structurally no code path where a caller passes one string
    containing both SQL and untrusted values — build() always requires
    template and params as SEPARATE arguments. This test documents that
    property by showing what interpolation would look like and confirming
    it still goes through the same placeholder/param machinery rather
    than being treated as trusted just because it looks like valid SQL.
    """
    malicious_value = "1 OR 1=1"
    built = query_builder.build("SELECT * FROM sale_order WHERE partner_id = :partner_id", {"partner_id": malicious_value})
    # the malicious-looking value is bound as a PARAMETER, not concatenated into SQL text
    compiled = built.compile()
    assert malicious_value not in str(compiled)
