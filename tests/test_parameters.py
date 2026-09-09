import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from mcp import Client

from data_mcp.config import ParquetRoot, Settings
from data_mcp.data import DataStore
from data_mcp.ontology import Metric, SemanticLayer
from data_mcp.parameters import postgres_bindings
from data_mcp.server import create_server
from data_mcp.sql import DataError

PARAMETER_SQL = (
    "SELECT COALESCE(SUM(value), 0) AS total FROM data "
    "WHERE CAST(day AS DATE) >= $start_day AND CAST(day AS DATE) < $end_day "
    "AND category = $category AND value >= $minimum AND active = $active"
)
PARAMETERS = """
[[metrics.total.date_windows]]
start = "start_day"
end = "end_day"
max_days = 31
[metrics.total.parameters.start_day]
type = "date"
description = "Inclusive start, calendar date in metric timezone"
minimum = 2026-01-01
maximum = 2026-12-31
[metrics.total.parameters.end_day]
type = "date"
description = "Exclusive end, calendar date in metric timezone"
minimum = 2026-01-01
maximum = 2027-01-01
[metrics.total.parameters.category]
type = "string"
description = "Category"
max_length = 128
[metrics.total.parameters.minimum]
type = "integer"
description = "Minimum included value"
minimum = -100
maximum = 100
[metrics.total.parameters.active]
type = "boolean"
description = "Required active flag"
"""
VALUES: dict[str, object] = {
    "start_day": "2026-01-01",
    "end_day": "2026-02-01",
    "category": "a",
    "minimum": 0,
    "active": True,
}


def parameter_manifest(tmp_path: Path, query: str = PARAMETER_SQL) -> Path:
    path = tmp_path.resolve() / "metrics.toml"
    path.write_text(
        """schema_version = 1
[metrics.total]
backend = "parquet"
source = "fixture"
paths = ["rows.parquet"]
description = "Synthetic filtered sum"
grain = "one total"
units = "units"
timezone = "UTC"
owner = "synthetic-development"
reviewed_on = 2026-09-09
expected_columns = ["total"]
"""
        + f"sql = {json.dumps(query)}\n"
        + PARAMETERS
    )
    return path


def configured(tmp_path: Path) -> tuple[DataStore, SemanticLayer]:
    path = parameter_manifest(tmp_path)
    settings = Settings(
        parquet={"fixture": ParquetRoot(path=tmp_path.resolve())},
        ontology_file=path,
    )
    store = DataStore(settings)
    store.write_parquet(
        "fixture",
        "rows.parquet",
        json.dumps(
            [
                {"day": "2026-01-01", "category": "a", "value": 3, "active": True},
                {"day": "2026-01-31", "category": "a", "value": 5, "active": True},
                {"day": "2026-02-01", "category": "a", "value": 7, "active": True},
                {"day": "2026-01-10", "category": "a", "value": 100, "active": False},
                {
                    "day": "2026-01-10",
                    "category": "x' OR TRUE --",
                    "value": 11,
                    "active": True,
                },
            ]
        ),
    )
    return store, SemanticLayer(settings)


def test_bound_values_and_date_window_execute_without_sql_interpolation(
    tmp_path: Path,
) -> None:
    store, layer = configured(tmp_path)
    result = layer.run_metric(store, "total", layer.revision, VALUES)
    assert result["rows"] == [[8]]
    assert result["parameters"] == VALUES
    assert result["submitted_sql"] == PARAMETER_SQL
    assert "$start_day" in result["normalized_sql"]
    values = {**VALUES, "start_day": "2026-02-01", "end_day": "2026-03-01"}
    assert layer.run_metric(store, "total", layer.revision, values)["rows"] == [[7]]
    assert layer.run_metric(
        store, "total", layer.revision, {**VALUES, "category": "x' OR TRUE --"}
    )["rows"] == [[11]]
    assert layer.run_metric(
        store, "total", layer.revision, {**VALUES, "active": False}
    )["rows"] == [[100]]
    assert (
        layer.context()["metrics"]["total"]["parameters"]["start_day"]["type"] == "date"
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"extra": "no"},
        {"minimum": True},
        {"minimum": "1"},
        {"minimum": 1.0},
        {"minimum": 101},
        {"minimum": None},
        {"active": 1},
        {"active": "true"},
        {"category": ["a"]},
        {"category": "a" * 129},
        {"category": "a\0b"},
        {"start_day": "20260101"},
        {"start_day": "2026-01-01T00:00:00Z"},
        {"start_day": "2026-02-30"},
        {"start_day": "2025-12-31"},
        {"end_day": "2026-01-01"},
        {"start_day": "2026-02-02"},
        {"end_day": "2026-03-01"},
    ],
)
def test_invalid_values_fail_before_database_access(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    store, layer = configured(tmp_path)
    with patch.object(store, "query_parquet") as query:
        with pytest.raises(DataError):
            layer.run_metric(store, "total", layer.revision, {**VALUES, **changes})
        query.assert_not_called()
    with pytest.raises(DataError):
        layer.run_metric(store, "total", layer.revision)


def test_invalid_parameter_contracts_and_stale_revision(tmp_path: Path) -> None:
    store, layer = configured(tmp_path)
    metric = layer.context()["metrics"]["total"]
    for changes in (
        {"sql": PARAMETER_SQL.replace("$minimum", "$unknown")},
        {"sql": "SELECT ? AS total FROM data"},
        {"date_windows": [{"start": "category", "end": "end_day", "max_days": 31}]},
        {"date_windows": [{"start": "start_day", "end": "start_day", "max_days": 31}]},
        {
            "parameters": {
                "minimum": {
                    "type": "integer",
                    "description": "test",
                    "minimum": 5,
                    "maximum": 1,
                }
            }
        },
    ):
        with pytest.raises(ValueError):
            Metric.model_validate({**metric, **changes})
    path = store.settings.ontology_file
    assert path is not None
    path.write_text(path.read_text().replace("max_days = 31", "max_days = 30"))
    fresh = SemanticLayer(store.settings)
    assert fresh.revision != layer.revision
    with pytest.raises(DataError, match="revision"):
        fresh.run_metric(store, "total", layer.revision, VALUES)
    with pytest.raises(DataError, match="window"):
        fresh.run_metric(store, "total", fresh.revision, VALUES)


def test_postgres_ast_binding_keeps_literals_and_repeated_parameters() -> None:
    sql = "SELECT %(value)s, '%(value)s', 5 % 2, %(value)s, %(other)s"
    query, values = postgres_bindings(sql, {"value": "x' OR TRUE --", "other": 2})
    assert query == "SELECT $2, '%(value)s', 5 % 2, $2, $1"
    assert values == [2, "x' OR TRUE --"]
    for bad in ("SELECT $1", "SELECT %s", "SELECT %(other)s"):
        with pytest.raises(DataError):
            postgres_bindings(bad, {"value": 1})


def test_metric_parameters_over_mcp(tmp_path: Path) -> None:
    store, layer = configured(tmp_path)
    settings = store.settings.model_copy(update={"access_mode": "analysis"})

    async def run() -> None:
        async with Client(create_server(settings)) as client:
            result = await client.call_tool(
                "run_metric",
                {
                    "name": "total",
                    "revision": layer.revision,
                    "parameters": VALUES,
                },
            )
            assert not result.is_error
            assert result.structured_content is not None
            assert result.structured_content["rows"] == [[8]]
            bad = await client.call_tool(
                "run_metric",
                {
                    "name": "total",
                    "revision": layer.revision,
                    "parameters": {**VALUES, "minimum": True},
                },
            )
            assert bad.is_error

    asyncio.run(run())


def test_choice_bounds_and_parameter_payload_limit(tmp_path: Path) -> None:
    from data_mcp.parameters import StringParameter, validate_values

    spec = StringParameter(
        type="string", description="Selection", max_length=8, choices=("a", "b")
    )
    assert validate_values({"choice": spec}, (), {"choice": "a"}) == {"choice": "a"}
    with pytest.raises(DataError):
        validate_values({"choice": spec}, (), {"choice": "c"})
    for choices in (("a", "a"), ("too-long-value",), ("x\0",)):
        with pytest.raises(ValueError):
            StringParameter(
                type="string", description="Selection", max_length=8, choices=choices
            )
    large = StringParameter(type="string", description="Text", max_length=1024)
    with pytest.raises(DataError, match="JSON"):
        validate_values(
            {f"p{i}": large for i in range(9)},
            (),
            {f"p{i}": "a" * 1024 for i in range(9)},
        )


def test_fixed_only_catalog_keeps_original_tool_schema(tmp_path: Path) -> None:
    path = parameter_manifest(tmp_path, "SELECT 1 AS total FROM data")
    path.write_text(path.read_text().split("[[metrics.total.date_windows]]")[0])
    settings = Settings(
        ontology_file=path, parquet={"fixture": ParquetRoot(path=tmp_path.resolve())}
    )
    layer = SemanticLayer(settings)
    assert not layer.has_parameters
    assert "parameters" not in layer.context()["metrics"]["total"]
    assert "date_windows" not in layer.context()["metrics"]["total"]

    async def run() -> None:
        async with Client(create_server(settings)) as client:
            catalog = await client.list_tools()
            tool = next(t for t in catalog.tools if t.name == "run_metric")
            assert set(tool.input_schema["properties"]) == {"name", "revision"}

    asyncio.run(run())


@pytest.mark.parametrize("minimum", [0, True, "2026-01-01T00:00:00Z", "20260101"])
def test_date_bounds_never_coerce_timestamps(minimum: object) -> None:
    from data_mcp.parameters import DateParameter

    with pytest.raises(ValueError):
        DateParameter.model_validate(
            {
                "type": "date",
                "description": "Date",
                "minimum": minimum,
                "maximum": "2026-12-31",
            }
        )
