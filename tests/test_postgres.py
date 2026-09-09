"""Opt-in integration tests; the DSN must name a disposable test database."""

import os
from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from data_mcp.config import PostgresSource, Settings
from data_mcp.data import DataStore
from data_mcp.sql import DataError


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch) -> Generator[tuple[DataStore, str]]:
    dsn = os.getenv("DATA_MCP_TEST_DSN")
    if not dsn:
        pytest.skip("Set DATA_MCP_TEST_DSN to a disposable PostgreSQL database")
    monkeypatch.setenv("DATA_MCP_TEST_DSN", dsn)
    schema = "mcp_test_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        conn.execute(
            sql.SQL("CREATE TABLE {}.items (id int PRIMARY KEY, value numeric)").format(
                sql.Identifier(schema)
            )
        )
    store = DataStore(
        Settings(
            postgres={
                "test": PostgresSource(dsn_env="DATA_MCP_TEST_DSN", sslmode="disable"),
                "ro": PostgresSource(
                    dsn_env="DATA_MCP_TEST_DSN", sslmode="disable", writable=False
                ),
            },
            query_timeout_seconds=1,
            max_rows=2,
        )
    )
    try:
        yield store, schema
    finally:
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )


def test_postgres_crud_commit_and_rollback(database: tuple[DataStore, str]) -> None:
    store, schema = database
    table = schema + ".items"
    assert store.execute_postgres("test", f"INSERT INTO {table} VALUES (1, 2.50)") == {
        "committed": True,
        "affected_rows": 1,
    }
    result = store.query_postgres("test", f"SELECT id, value FROM {table}")
    assert result["rows"] == [[1, "2.50"]]
    with pytest.raises(psycopg.errors.UniqueViolation):
        store.execute_postgres("test", f"INSERT INTO {table} VALUES (2, 4), (1, 5)")
    assert store.query_postgres("test", f"SELECT count(*) FROM {table}")["rows"] == [
        [1]
    ]
    assert (
        store.execute_postgres("test", f"UPDATE {table} SET value=3")["affected_rows"]
        == 1
    )
    assert store.execute_postgres("test", f"DELETE FROM {table}")["affected_rows"] == 1
    assert store.query_postgres("test", f"SELECT * FROM {table}")["rows"] == []


def test_postgres_readonly_timeout_and_limits(database: tuple[DataStore, str]) -> None:
    store, schema = database
    table = schema + ".items"
    with pytest.raises(DataError, match="read-only"):
        store.execute_postgres("ro", f"INSERT INTO {table} VALUES (1, 1)")
    result = store.query_postgres("test", "SELECT generate_series(1, 10)")
    assert result["rows"] == [[1], [2]]
    assert result["truncated"]
    assert store.query_postgres(
        "test", "SELECT current_setting('transaction_read_only')"
    )["rows"] == [["on"]]
    with pytest.raises(psycopg.errors.QueryCanceled):
        store.query_postgres("test", "SELECT pg_sleep(5)")


def test_postgres_mcp_roundtrip(database: tuple[DataStore, str]) -> None:
    import asyncio

    from mcp import Client

    from data_mcp.server import create_server

    store, schema = database

    async def run() -> None:
        async with Client(create_server(store.settings)) as client:
            result = await client.call_tool(
                "execute_postgres",
                {
                    "source": "test",
                    "sql": f"INSERT INTO {schema}.items VALUES (1, 5)",
                },
            )
            assert not result.is_error
            result = await client.call_tool(
                "describe_postgres",
                {
                    "source": "test",
                    "schema": schema,
                    "table": "items",
                },
            )
            assert result.structured_content is not None
            assert [r[0] for r in result.structured_content["rows"]] == ["id", "value"]
            result = await client.call_tool(
                "query_postgres",
                {
                    "source": "test",
                    "sql": f"SELECT value FROM {schema}.items",
                },
            )
            assert result.structured_content is not None
            assert result.structured_content["rows"] == [["5"]]

    asyncio.run(run())


def test_governed_postgres_metric(
    database: tuple[DataStore, str], tmp_path: Path
) -> None:
    import json

    from data_mcp.ontology import SemanticLayer

    store, schema = database
    store.execute_postgres("test", f"INSERT INTO {schema}.items VALUES (1, 2.50)")
    path = tmp_path / "approved.toml"
    path.write_text(
        'schema_version=1\n[metrics.total]\nbackend="postgres"\nsource="test"\n'
        'description="Fixture total"\ngrain="one row"\nunits="units"\n'
        'timezone="America/New_York"\nowner="test"\nreviewed_on=2026-09-06\n'
        'expected_columns=["total", "zone"]\n'
        + "sql="
        + json.dumps(
            "SELECT SUM(value) AS total, current_setting('TimeZone') AS zone "
            f"FROM {schema}.items"
        )
        + "\n"
    )
    settings = store.settings.model_copy(
        update={
            "ontology_file": path,
            "access_mode": "analysis",
        }
    )
    analysis = DataStore(settings)
    layer = SemanticLayer(settings)
    result = layer.run_metric(analysis, "total", layer.revision)
    assert result["rows"] == [["2.50", "America/New_York"]]
    with pytest.raises(DataError, match="read-only"):
        analysis.execute_postgres("test", f"DELETE FROM {schema}.items")


def test_postgres_bound_metric_values(
    database: tuple[DataStore, str], tmp_path: Path
) -> None:
    import asyncio
    import json

    from mcp import Client

    from data_mcp.ontology import SemanticLayer
    from data_mcp.server import create_server

    store, _ = database
    query = (
        "SELECT %(label)s::text AS label, '%(label)s' AS literal, "
        "%(minimum)s::int % 2 AS remainder, %(start_day)s::date AS day, "
        "%(active)s::boolean AS active, %(label)s::text AS repeated, "
        "current_setting('transaction_read_only') AS readonly"
    )
    path = tmp_path.resolve() / "parameters.toml"
    path.write_text(
        """schema_version=1
[metrics.filtered]
backend="postgres"
source="test"
description="Synthetic bound value checks"
grain="one row"
units="mixed test values"
timezone="UTC"
owner="test"
reviewed_on=2026-09-09
expected_columns=[
  "label", "literal", "remainder", "day", "active", "repeated", "readonly"
]
"""
        + f"sql={json.dumps(query)}\n"
        + """
[metrics.filtered.parameters.label]
type="string"
description="Bound text"
max_length=128
[metrics.filtered.parameters.minimum]
type="integer"
description="Bound integer"
minimum=0
maximum=10
[metrics.filtered.parameters.start_day]
type="date"
description="Bound calendar date"
minimum=2026-01-01
maximum=2026-12-31
[metrics.filtered.parameters.active]
type="boolean"
description="Bound flag"
"""
    )
    settings = store.settings.model_copy(
        update={"ontology_file": path, "access_mode": "analysis"}
    )
    layer = SemanticLayer(settings)
    values: dict[str, object] = {
        "label": "x' OR TRUE --",
        "minimum": 5,
        "start_day": "2026-01-01",
        "active": True,
    }
    expected = [
        ["x' OR TRUE --", "%(label)s", 1, "2026-01-01", True, "x' OR TRUE --", "on"]
    ]
    result = layer.run_metric(DataStore(settings), "filtered", layer.revision, values)
    assert result["rows"] == expected
    assert result["parameters"] == values
    assert "%(minimum)s" in result["submitted_sql"]
    assert "$3" in result["normalized_sql"]
    # Streaming row limit remains active with raw server-side bindings.
    result = store.query_postgres(
        "test", "SELECT generate_series(1, %(count)s)", parameters={"count": 10}
    )
    assert result["rows"] == [[1], [2]]
    assert result["truncated"] is True

    async def run() -> None:
        async with Client(create_server(settings)) as client:
            result = await client.call_tool(
                "run_metric",
                {"name": "filtered", "revision": layer.revision, "parameters": values},
            )
            assert not result.is_error
            assert result.structured_content is not None
            assert result.structured_content["rows"] == expected

    asyncio.run(run())


@pytest.mark.parametrize(
    "expression,sql_type,expected",
    [
        ("3::int4", "int4", 3),
        ("3.25::numeric(12,2)", "numeric(12,2)", "3.25"),
        ("3.25::numeric", "numeric", "3.25"),
        (
            "12345678901234567890.123456789012345678::numeric(38,18)",
            "numeric(38,18)",
            "12345678901234567890.123456789012345678",
        ),
        ("3.25::float8", "float8", 3.25),
        ("'3'::text", "text", "3"),
        ("true", "bool", True),
        ("DATE '2026-01-01'", "date", "2026-01-01"),
        ("TIMESTAMP '2026-01-01 00:00:00'", "timestamp", "2026-01-01 00:00:00"),
        (
            "TIMESTAMPTZ '2026-01-01 00:00:00+00'",
            "timestamptz",
            "2026-01-01 00:00:00+00:00",
        ),
    ],
)
def test_postgres_native_output_types(
    database: tuple[DataStore, str], expression: str, sql_type: str, expected: object
) -> None:
    from data_mcp.output import OutputColumn

    store, _ = database
    contract = (OutputColumn(name="total", sql_type=sql_type, nullable=False),)
    result = store.query_postgres(
        "test",
        f"SELECT {expression} AS total",
        timezone="UTC",
        output_contract=contract,
    )
    assert result["rows"] == [[expected]]
    assert result["column_types"] == [sql_type]
    # Parameterized raw server cursor applies the same contract as the fixed path.
    result = store.query_postgres(
        "test",
        "SELECT %(value)s::int4 AS total",
        parameters={"value": 3},
        output_contract=(OutputColumn(name="total", sql_type="int4", nullable=False),),
    )
    assert result["rows"] == [[3]]


@pytest.mark.parametrize(
    "sql,sql_type",
    [
        ("SELECT '3'::text AS total WHERE FALSE", "int4"),
        ("SELECT NULL::int4 AS total", "int4"),
        ("SELECT 'NaN'::numeric AS total", "numeric"),
        ("SELECT 'Infinity'::numeric AS total", "numeric"),
        ("SELECT '-Infinity'::float8 AS total", "float8"),
        ("SELECT 3.25::numeric(13,2) AS total", "numeric(12,2)"),
        ("SELECT ARRAY[1] AS total WHERE FALSE", "int4"),
    ],
)
def test_postgres_output_violations(
    database: tuple[DataStore, str], sql: str, sql_type: str
) -> None:
    from data_mcp.output import OutputColumn

    store, _ = database
    with pytest.raises(DataError):
        store.query_postgres(
            "test",
            sql,
            output_contract=(
                OutputColumn(name="total", sql_type=sql_type, nullable=False),
            ),
        )


def test_postgres_metric_output_contract(
    database: tuple[DataStore, str], tmp_path: Path
) -> None:
    import asyncio
    import json

    from mcp import Client

    from data_mcp.ontology import SemanticLayer
    from data_mcp.server import create_server

    store, schema = database
    store.execute_postgres("test", f"INSERT INTO {schema}.items VALUES (1, 3.25)")
    path = tmp_path.resolve() / "output.toml"
    path.write_text(
        """schema_version=1
[metrics.total]
backend="postgres"
source="test"
description="Synthetic typed numeric result"
grain="one row"
units="units"
timezone="UTC"
owner="synthetic-test"
reviewed_on=2026-09-09
expected_columns=["total"]
"""
        + f"sql={json.dumps(f'SELECT value AS total FROM {schema}.items')}\n"
        + """
[[metrics.total.output_contract]]
name="total"
sql_type="numeric"
nullable=false
"""
    )
    settings = store.settings.model_copy(
        update={"ontology_file": path, "access_mode": "analysis"}
    )
    layer = SemanticLayer(settings)

    async def run() -> None:
        async with Client(create_server(settings)) as client:
            result = await client.call_tool(
                "run_metric", {"name": "total", "revision": layer.revision}
            )
            assert not result.is_error
            assert result.structured_content is not None
            assert result.structured_content["rows"] == [["3.25"]]
            assert result.structured_content["output_contract_verified"] is True

    asyncio.run(run())
    with psycopg.connect(os.environ["DATA_MCP_TEST_DSN"], autocommit=True) as conn:
        conn.execute(
            sql.SQL(
                "ALTER TABLE {}.items ALTER COLUMN value TYPE text USING value::text"
            ).format(sql.Identifier(schema))
        )
    with pytest.raises(DataError, match="SQL types changed"):
        layer.run_metric(DataStore(settings), "total", layer.revision)
