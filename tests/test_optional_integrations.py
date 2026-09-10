"""Opt-in integration tests for disposable MySQL, MongoDB, and S3 services."""

import importlib
import os
import time
from collections.abc import Callable, Generator
from typing import Any
from urllib.parse import unquote, urlparse
from uuid import uuid4

import pymysql
import pytest

from data_mcp.config import MongoSource, MySQLSource, S3Source, Settings
from data_mcp.data import DataStore


def wait_for_service(
    check: Callable[[], object], *, timeout_seconds: float = 30
) -> None:
    """Wait for a just-started disposable service to accept requests."""
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            check()
        except Exception as error:  # noqa: BLE001 - drivers expose distinct errors
            last_error = error
            time.sleep(0.5)
        else:
            return
    raise RuntimeError("Timed out waiting for disposable test service") from last_error


def mysql_connection(dsn: str, *, autocommit: bool = False) -> pymysql.Connection:
    parsed = urlparse(dsn)
    return pymysql.connect(
        host=parsed.hostname or "",
        port=parsed.port or 3306,
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        database=unquote(parsed.path.removeprefix("/")),
        connect_timeout=5,
        autocommit=autocommit,
    )


@pytest.fixture
def mysql_store(monkeypatch: pytest.MonkeyPatch) -> Generator[tuple[DataStore, str]]:
    dsn = os.getenv("DATA_MCP_MYSQL_TEST_DSN")
    if not dsn:
        pytest.skip("Set DATA_MCP_MYSQL_TEST_DSN to a disposable MySQL database")
    monkeypatch.setenv("DATA_MCP_MYSQL_TEST_DSN", dsn)
    wait_for_service(lambda: mysql_connection(dsn).close())
    table = "mcp_test_" + uuid4().hex
    with (
        mysql_connection(dsn, autocommit=True) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            f"CREATE TABLE {table} "
            "(id BIGINT PRIMARY KEY, value DECIMAL(12,2), label VARCHAR(64))"
        )
    store = DataStore(
        Settings(
            mysql={
                "test": MySQLSource(dsn_env="DATA_MCP_MYSQL_TEST_DSN", tls=False),
                "ro": MySQLSource(
                    dsn_env="DATA_MCP_MYSQL_TEST_DSN", tls=False, writable=False
                ),
            },
            max_rows=2,
        )
    )
    try:
        yield store, table
    finally:
        with (
            mysql_connection(dsn, autocommit=True) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(f"DROP TABLE IF EXISTS {table}")


def test_mysql_live_crud_rollback_and_readonly(
    mysql_store: tuple[DataStore, str],
) -> None:
    store, table = mysql_store
    assert store.execute_mysql(
        "test", f"INSERT INTO {table} VALUES (1, 2.50, 'one')"
    ) == {"committed": True, "affected_rows": 1}
    assert store.query_mysql("test", f"SELECT id, value, label FROM {table}")[
        "rows"
    ] == [[1, "2.50", "one"]]
    with pytest.raises(pymysql.err.IntegrityError):
        store.execute_mysql(
            "test", f"INSERT INTO {table} VALUES (2, 4, 'two'), (1, 5, 'bad')"
        )
    assert store.query_mysql("test", f"SELECT COUNT(*) FROM {table}")["rows"] == [[1]]
    with store.mysql("test") as connection, connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION READ ONLY")
        cursor.execute("SELECT 1")
        with pytest.raises(pymysql.err.OperationalError, match="READ ONLY"):
            cursor.execute(f"INSERT INTO {table} VALUES (3, 6, 'blocked')")
        connection.rollback()
    assert (
        store.execute_mysql(
            "test", f"UPDATE {table} SET label = 'updated' WHERE id = 1"
        )["affected_rows"]
        == 1
    )
    assert (
        store.execute_mysql("test", f"DELETE FROM {table} WHERE id = 1")[
            "affected_rows"
        ]
        == 1
    )


@pytest.fixture
def mongo_store(monkeypatch: pytest.MonkeyPatch) -> Generator[tuple[DataStore, str]]:
    uri = os.getenv("DATA_MCP_MONGODB_TEST_URI")
    if not uri:
        pytest.skip("Set DATA_MCP_MONGODB_TEST_URI to a disposable MongoDB service")
    monkeypatch.setenv("DATA_MCP_MONGODB_TEST_URI", uri)
    collection = "mcp_test_" + uuid4().hex
    pymongo: Any = importlib.import_module("pymongo")
    client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=1000)
    try:
        wait_for_service(lambda: client.admin.command("ping"))
    finally:
        client.close()
    store = DataStore(
        Settings(
            mongodb={
                "test": MongoSource(
                    uri_env="DATA_MCP_MONGODB_TEST_URI",
                    database="data_mcp_test",
                    tls=False,
                )
            }
        )
    )
    try:
        yield store, collection
    finally:
        client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=5000)
        with client:
            client["data_mcp_test"].drop_collection(collection)


def test_mongodb_live_heterogeneous_crud(
    mongo_store: tuple[DataStore, str],
) -> None:
    store, collection = mongo_store
    result = store.insert_mongodb(
        "test", collection, '[{"kind":"first","value":1},{"kind":"second"}]'
    )
    assert result["acknowledged"] is True
    assert result["inserted_count"] == 2
    documents = store.query_mongodb(
        "test", collection, "{}", '{"_id":0,"kind":1,"value":1}'
    )["documents"]
    assert documents == [
        {"kind": "first", "value": 1},
        {"kind": "second"},
    ]
    assert (
        store.update_mongodb(
            "test", collection, '{"kind":"second"}', '{"$set":{"value":2}}'
        )["modified_count"]
        == 1
    )
    assert (
        store.delete_mongodb("test", collection, '{"value":{"$gte":1}}', many=True)[
            "deleted_count"
        ]
        == 2
    )


@pytest.fixture
def s3_store() -> Generator[tuple[DataStore, str]]:
    endpoint = os.getenv("DATA_MCP_S3_TEST_ENDPOINT")
    if not endpoint:
        pytest.skip("Set DATA_MCP_S3_TEST_ENDPOINT to a disposable S3 service")
    bucket = "data-mcp-test-" + uuid4().hex
    boto3: Any = importlib.import_module("boto3")
    client = boto3.client("s3", endpoint_url=endpoint, region_name="us-east-1")
    wait_for_service(client.list_buckets)
    client.create_bucket(Bucket=bucket)
    store = DataStore(
        Settings(
            s3={
                "test": S3Source(
                    bucket=bucket,
                    prefix="suite",
                    endpoint_url=endpoint,
                    allow_insecure_endpoint=endpoint.startswith("http://"),
                    writable=True,
                )
            }
        )
    )
    try:
        yield store, bucket
    finally:
        page = client.list_objects_v2(Bucket=bucket)
        objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
        if objects:
            client.delete_objects(Bucket=bucket, Delete={"Objects": objects})
        client.delete_bucket(Bucket=bucket)


@pytest.mark.parametrize("extension", ["csv", "parquet", "jsonl"])
def test_s3_live_file_roundtrip(
    s3_store: tuple[DataStore, str], extension: str
) -> None:
    store, _ = s3_store
    client_error: Any = importlib.import_module("botocore.exceptions").ClientError
    path = f"nested/items.{extension}"
    assert store.write_s3("test", path, '[{"value":7}]')["mode"] == "create"
    with pytest.raises(client_error):
        store.write_s3("test", path, '[{"value":8}]')
    assert store.list_s3_objects("test", "nested")["objects"] == [
        {
            "key": path,
            "format": "json" if extension == "jsonl" else extension,
            "bytes": store.list_s3_objects("test", "nested")["objects"][0]["bytes"],
        }
    ]
    assert store.query_s3("test", [path], "SELECT value FROM data")["rows"] == [[7]]
    assert store.write_s3("test", path, '[{"value":8}]', "replace")["mode"] == "replace"
    assert store.query_s3("test", ["nested"], "SELECT SUM(value) FROM data")[
        "rows"
    ] == [[8]]
