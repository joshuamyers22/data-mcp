import asyncio
import json
import sys
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from data_mcp.config import ParquetRoot, Settings
from data_mcp.server import create_server


def test_stdio_discovery_write_query(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(f"[parquet.raw]\npath={json.dumps(str(tmp_path))}\n")

    async def run() -> None:
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "data_mcp.cli", "--config", str(config)]
        )
        async with Client(params) as client:
            tools = await client.list_tools()
            assert {t.name for t in tools.tools} >= {
                "query_parquet",
                "execute_postgres",
            }
            result = await client.call_tool(
                "write_parquet",
                {
                    "root": "raw",
                    "path": "a.parquet",
                    "rows_json": '[{"id":7}]',
                },
            )
            assert not result.is_error
            result = await client.call_tool(
                "query_parquet",
                {
                    "root": "raw",
                    "paths": ["a.parquet"],
                    "sql": "SELECT id FROM data",
                },
            )
            assert result.structured_content is not None
            assert result.structured_content["rows"] == [[7]]
            result = await client.call_tool(
                "write_parquet",
                {
                    "root": "raw",
                    "path": "a.parquet",
                    "rows_json": '[{"id":8}]',
                },
            )
            assert result.is_error

    asyncio.run(run())


def test_mcp_errors_do_not_expose_data(tmp_path: Path) -> None:
    (tmp_path / "bad.parquet").write_text("PRIVATE_SENTINEL")
    server = create_server(Settings(parquet={"raw": ParquetRoot(path=tmp_path)}))

    async def run() -> None:
        async with Client(server) as client:
            result = await client.call_tool(
                "query_parquet",
                {
                    "root": "raw",
                    "paths": ["bad.parquet"],
                    "sql": "SELECT * FROM data",
                },
            )
            assert result.is_error
            assert "PRIVATE_SENTINEL" not in str(result)
            assert str(tmp_path) not in str(result)

    asyncio.run(run())


def test_operation_logs_exclude_driver_details(tmp_path: Path) -> None:
    import contextlib
    import io
    from unittest.mock import patch

    from data_mcp.data import DataStore

    server = create_server(Settings(parquet={"raw": ParquetRoot(path=tmp_path)}))
    captured = io.StringIO()

    async def run() -> None:
        async with Client(server) as client:
            result = await client.call_tool(
                "query_parquet",
                {
                    "root": "raw",
                    "paths": ["a.parquet"],
                    "sql": "SELECT 1",
                },
            )
            assert result.is_error
            assert "CREDENTIAL_SENTINEL" not in str(result)

    with (
        patch.object(
            DataStore, "query_parquet", side_effect=RuntimeError("CREDENTIAL_SENTINEL")
        ),
        contextlib.redirect_stderr(captured),
    ):
        asyncio.run(run())
    assert "CREDENTIAL_SENTINEL" not in captured.getvalue()
    events = [
        json.loads(line)
        for line in captured.getvalue().splitlines()
        if line.startswith("{")
    ]
    assert any(
        e["event"] == "data_operation" and e["outcome"] == "error" for e in events
    )
