import asyncio
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from mcp import Client

from data_mcp.config import ParquetRoot, Settings
from data_mcp.data import DataStore
from data_mcp.ontology import Metric, SemanticLayer
from data_mcp.output import OutputColumn, check_row
from data_mcp.server import create_server
from data_mcp.sql import DataError


def configured(
    tmp_path: Path, sql: str, sql_type: str, nullable: bool = False
) -> tuple[DataStore, SemanticLayer]:
    path = tmp_path.resolve() / "metric.toml"
    path.write_text(
        """schema_version=1
[metrics.total]
backend="parquet"
source="fixture"
paths=["rows.parquet"]
description="Synthetic output contract"
grain="one row"
units="units"
timezone="UTC"
owner="synthetic-development"
reviewed_on=2026-09-09
expected_columns=["total"]
"""
        + f"sql={json.dumps(sql)}\n"
        + """[[metrics.total.output_contract]]
name="total"
"""
        + f"sql_type={json.dumps(sql_type)}\nnullable={str(nullable).lower()}\n"
    )
    settings = Settings(
        parquet={"fixture": ParquetRoot(path=tmp_path.resolve())}, ontology_file=path
    )
    store = DataStore(settings)
    store.write_parquet("fixture", "rows.parquet", '[{"value":3}]')
    return store, SemanticLayer(settings)


@pytest.mark.parametrize(
    "expression,sql_type,expected",
    [
        ("SUM(value)", "HUGEINT", 3),
        ("CAST(value AS DOUBLE)", "DOUBLE", 3.0),
        ("CAST(value AS DECIMAL(12,2))", "DECIMAL(12,2)", "3.00"),
        (
            "CAST('12345678901234567890.123456789012345678' AS DECIMAL(38,18))",
            "DECIMAL(38,18)",
            "12345678901234567890.123456789012345678",
        ),
        ("CAST(value AS VARCHAR)", "VARCHAR", "3"),
        ("value > 0", "BOOLEAN", True),
        ("CAST('2026-01-01' AS DATE)", "DATE", "2026-01-01"),
        (
            "CAST('2026-01-01 00:00:00' AS TIMESTAMP)",
            "TIMESTAMP",
            "2026-01-01 00:00:00",
        ),
        (
            "CAST('2026-01-01 00:00:00+00' AS TIMESTAMPTZ)",
            "TIMESTAMP WITH TIME ZONE",
            "2026-01-01 00:00:00+00:00",
        ),
    ],
)
def test_native_types_checked_before_serialization(
    tmp_path: Path, expression: str, sql_type: str, expected: object
) -> None:
    store, layer = configured(
        tmp_path, f"SELECT {expression} AS total FROM data", sql_type
    )
    result = layer.run_metric(store, "total", layer.revision)
    assert result["rows"] == [[expected]]
    assert result["column_types"] == [sql_type]
    assert result["output_contract_verified"] is True


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT CAST(value AS VARCHAR) AS total FROM data",
        "SELECT CAST(value AS VARCHAR) AS total FROM data WHERE FALSE",
        "SELECT NULL::VARCHAR AS total FROM data",
    ],
)
def test_type_drift_including_empty_or_null_results_fails(
    tmp_path: Path, sql: str
) -> None:
    store, layer = configured(tmp_path, sql, "BIGINT", nullable=True)
    with pytest.raises(DataError, match="SQL types changed"):
        layer.run_metric(store, "total", layer.revision)


def test_same_query_detects_replaced_parquet_type(tmp_path: Path) -> None:
    store, layer = configured(tmp_path, "SELECT value AS total FROM data", "BIGINT")
    assert layer.run_metric(store, "total", layer.revision)["rows"] == [[3]]
    store.write_parquet("fixture", "rows.parquet", '[{"value":"3"}]', "replace")
    with pytest.raises(DataError, match="SQL types changed"):
        layer.run_metric(store, "total", layer.revision)


def test_null_and_empty_results_have_distinct_contracts(tmp_path: Path) -> None:
    store, layer = configured(
        tmp_path, "SELECT NULL::BIGINT AS total FROM data", "BIGINT"
    )
    with pytest.raises(DataError, match="unexpected null"):
        layer.run_metric(store, "total", layer.revision)
    path = store.settings.ontology_file
    assert path is not None
    path.write_text(path.read_text().replace("nullable=false", "nullable=true"))
    fresh = SemanticLayer(store.settings)
    assert fresh.revision != layer.revision
    assert fresh.run_metric(store, "total", fresh.revision)["rows"] == [[None]]
    with pytest.raises(DataError, match="revision"):
        fresh.run_metric(store, "total", layer.revision)
    path.write_text(path.read_text().replace("FROM data", "FROM data WHERE FALSE"))
    fresh = SemanticLayer(store.settings)
    assert fresh.run_metric(store, "total", fresh.revision)["rows"] == []


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_numbers_cannot_be_accepted_as_strings(
    tmp_path: Path, value: str
) -> None:
    store, layer = configured(
        tmp_path, f"SELECT CAST('{value}' AS DOUBLE) AS total FROM data", "DOUBLE"
    )
    with pytest.raises(DataError, match="nonfinite"):
        layer.run_metric(store, "total", layer.revision)
    # Existing ad hoc reads keep their documented string serialization.
    raw = store.query_parquet(
        "fixture",
        ["rows.parquet"],
        f"SELECT CAST('{value}' AS DOUBLE) AS total FROM data",
    )
    assert isinstance(raw["rows"][0][0], str)
    assert "column_types" not in raw


def test_decimal_precision_change_and_invalid_contract(tmp_path: Path) -> None:
    store, layer = configured(
        tmp_path,
        "SELECT CAST(value AS DECIMAL(13,2)) AS total FROM data",
        "DECIMAL(12,2)",
    )
    with pytest.raises(DataError, match="SQL types changed"):
        layer.run_metric(store, "total", layer.revision)
    metric = layer.context()["metrics"]["total"]
    for contract in [
        [{"name": "wrong", "sql_type": "BIGINT", "nullable": False}],
        [{"name": "total", "sql_type": "BIGINT[]", "nullable": False}],
        [{"name": "total", "sql_type": "DECIMAL(2,3)", "nullable": False}],
        [{"name": "total", "sql_type": "BIGINT", "nullable": "false"}],
    ]:
        with pytest.raises(ValueError):
            Metric.model_validate({**metric, "output_contract": contract})


def test_runtime_scalar_type_confusion_is_rejected() -> None:
    for sql_type, value in [("BIGINT", True), ("DOUBLE", "3.0"), ("BOOLEAN", 1)]:
        with pytest.raises(DataError, match="wrong-type"):
            check_row(
                (value,),
                (OutputColumn(name="total", sql_type=sql_type, nullable=False),),
                "parquet",
            )


def test_output_contract_mcp_and_truncation(tmp_path: Path) -> None:
    store, layer = configured(tmp_path, "SELECT value AS total FROM data", "BIGINT")
    store.write_parquet("fixture", "rows.parquet", '[{"value":4}]', "append")

    async def run() -> None:
        async with Client(create_server(store.settings)) as client:
            result = await client.call_tool(
                "run_metric", {"name": "total", "revision": layer.revision}
            )
            assert not result.is_error
            assert result.structured_content is not None
            assert result.structured_content["output_contract_verified"] is True
        settings = store.settings.model_copy(update={"max_rows": 1})
        async with Client(create_server(settings)) as client:
            result = await client.call_tool(
                "run_metric", {"name": "total", "revision": layer.revision}
            )
            assert result.is_error
            assert not result.structured_content

    asyncio.run(run())


def test_description_checked_before_fetch() -> None:
    from data_mcp.data import result_rows

    cursor = Mock()
    cursor.description = [("total", "VARCHAR")]
    with pytest.raises(DataError, match="SQL types changed"):
        result_rows(
            cursor,
            Settings(),
            output_contract=(
                OutputColumn(name="total", sql_type="BIGINT", nullable=False),
            ),
        )
    cursor.fetchone.assert_not_called()
