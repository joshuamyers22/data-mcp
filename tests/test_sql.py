import pytest

from data_mcp.sql import DataError, parquet_query


def test_boolean_connectors_are_sql_operators() -> None:
    sql = "SELECT * FROM data WHERE a = 1 AND (b = 2 OR NOT c IS NULL)"
    assert parquet_query(sql) == sql


@pytest.mark.parametrize("connector", ["AND", "OR"])
@pytest.mark.parametrize("call", ["getenv('HOME')", "query('SELECT 1')"])
def test_boolean_connectors_do_not_hide_unsafe_functions(
    connector: str, call: str
) -> None:
    with pytest.raises(DataError, match="unsupported"):
        parquet_query(f"SELECT * FROM data WHERE a = 1 {connector} {call} IS NOT NULL")
