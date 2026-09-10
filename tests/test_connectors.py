import io
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from data_mcp.config import (
    FileRoot,
    MongoSource,
    MySQLSource,
    ParquetRoot,
    S3Source,
    Settings,
)
from data_mcp.data import DataStore
from data_mcp.sql import DataError, statement


class FakeCursor:
    description = (("value",),)

    def __init__(self) -> None:
        self.rows: list[tuple[object, ...]] = []
        self.rowcount = 1

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, query: str) -> None:
        if query.startswith("SELECT"):
            self.rows = [(7,)]

    def fetchone(self) -> tuple[object, ...] | None:
        return self.rows.pop(0) if self.rows else None


class FakeMySQLConnection:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor()

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def test_mysql_dsn_tls_query_and_write(monkeypatch: pytest.MonkeyPatch) -> None:
    statement("SELECT 1", "mysql")  # Load the lazy dialect before import mocking.
    monkeypatch.setenv("MYSQL_DSN", "mysql://user:p%40ss@db.example/test")
    connections: list[FakeMySQLConnection] = []
    kwargs: list[dict[str, Any]] = []

    def connect(**values: Any) -> FakeMySQLConnection:
        kwargs.append(values)
        connection = FakeMySQLConnection()
        connections.append(connection)
        return connection

    store = DataStore(Settings(mysql={"main": MySQLSource(dsn_env="MYSQL_DSN")}))
    module = SimpleNamespace(connect=connect)
    with patch("data_mcp.data.importlib.import_module", return_value=module):
        assert store.query_mysql("main", "SELECT 7 AS value")["rows"] == [[7]]
        assert store.execute_mysql("main", "UPDATE items SET value = 8") == {
            "committed": True,
            "affected_rows": 1,
        }
    assert kwargs[0]["password"] == "p@ss"
    assert kwargs[0]["ssl_verify_identity"] is True
    assert connections[0].rolled_back is True
    assert connections[1].committed is True


class FakeMongoResult:
    acknowledged = True
    inserted_ids = ["one"]
    matched_count = 1
    modified_count = 1
    deleted_count = 1


class FakeMongoCollection:
    def find(self, *_: object) -> "FakeMongoCollection":
        return self

    def limit(self, _: int) -> list[dict[str, object]]:
        return [{"_id": "one", "value": 7}]

    def insert_many(self, *_: object, **__: object) -> FakeMongoResult:
        return FakeMongoResult()

    def update_one(self, *_: object) -> FakeMongoResult:
        return FakeMongoResult()

    def update_many(self, *_: object) -> FakeMongoResult:
        return FakeMongoResult()

    def delete_one(self, *_: object) -> FakeMongoResult:
        return FakeMongoResult()

    def delete_many(self, *_: object) -> FakeMongoResult:
        return FakeMongoResult()


class FakeMongoDatabase:
    def list_collection_names(self) -> list[str]:
        return ["items"]

    def __getitem__(self, _: str) -> FakeMongoCollection:
        return FakeMongoCollection()


class FakeMongoClient:
    def __init__(self, *_: object, **__: object) -> None:
        self.closed = False

    def __getitem__(self, _: str) -> FakeMongoDatabase:
        return FakeMongoDatabase()

    def close(self) -> None:
        self.closed = True


def test_mongodb_bounded_operations_and_guards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MONGO_URI", "mongodb://db.example")
    store = DataStore(
        Settings(mongodb={"main": MongoSource(uri_env="MONGO_URI", database="example")})
    )
    module = SimpleNamespace(MongoClient=FakeMongoClient)
    with patch("data_mcp.data.importlib.import_module", return_value=module):
        assert store.list_mongodb_collections("main")["collections"] == ["items"]
        assert store.query_mongodb("main", "items")["documents"][0]["value"] == 7
        assert (
            store.insert_mongodb("main", "items", '[{"value":7}]')["inserted_count"]
            == 1
        )
        assert (
            store.update_mongodb(
                "main", "items", '{"value":7}', '{"$set":{"value":8}}'
            )["modified_count"]
            == 1
        )
        assert (
            store.delete_mongodb("main", "items", '{"value":8}')["deleted_count"] == 1
        )
    with pytest.raises(DataError, match="JavaScript"):
        store.query_mongodb("main", "items", '{"$where":"true"}')
    with pytest.raises(DataError, match="allow_all"):
        store.update_mongodb("main", "items", "{}", '{"$set":{"value":8}}')


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, **kwargs: Any) -> dict[str, str]:
        key = str(kwargs["Key"])
        if kwargs.get("IfNoneMatch") == "*" and key in self.objects:
            raise RuntimeError("precondition failed")
        self.objects[key] = kwargs["Body"].read()
        return {"ETag": '"test-etag"'}

    def head_object(self, **kwargs: Any) -> dict[str, int]:
        value = self.objects[str(kwargs["Key"])]
        return {"ContentLength": len(value)}

    def get_object(self, **kwargs: Any) -> dict[str, object]:
        class Body(io.BytesIO):
            def iter_chunks(self, chunk_size: int) -> Iterator[bytes]:
                while chunk := self.read(chunk_size):
                    yield chunk

        return {"Body": Body(self.objects[str(kwargs["Key"])])}

    def list_objects_v2(self, **kwargs: Any) -> dict[str, object]:
        prefix = str(kwargs["Prefix"])
        return {
            "Contents": [
                {"Key": key, "Size": len(value)}
                for key, value in self.objects.items()
                if key.startswith(prefix)
            ],
            "IsTruncated": False,
        }


def test_s3_file_roundtrip(tmp_path: Path) -> None:
    del tmp_path  # The adapter owns its private staging directory.
    client = FakeS3Client()
    store = DataStore(
        Settings(
            s3={
                "lake": S3Source(
                    bucket="example-bucket", prefix="datasets", writable=True
                )
            }
        )
    )
    with patch.object(
        store, "_s3_client", return_value=(store.settings.s3["lake"], client)
    ):
        created = store.write_s3("lake", "items.csv", '[{"value":7}]')
        assert created["etag"] == "test-etag"
        client.objects["datasets/../../escape.csv"] = b"value\n9\n"
        assert store.list_s3_objects("lake")["objects"][0]["key"] == "items.csv"
        assert store.query_s3("lake", ["items.csv"], "SELECT value FROM data")[
            "rows"
        ] == [[7]]
        store.write_s3("lake", "items.csv", '[{"value":8}]', "replace")
        assert store.query_s3("lake", ["items.csv"], "SELECT value FROM data")[
            "rows"
        ] == [[8]]


def test_s3_stream_enforces_limit_if_object_grows() -> None:
    class GrowingS3Client(FakeS3Client):
        def head_object(self, **kwargs: Any) -> dict[str, int]:
            del kwargs
            return {"ContentLength": 1}

    client = GrowingS3Client()
    client.objects["large.csv"] = b"x" * 1048577
    store = DataStore(
        Settings(
            s3={"lake": S3Source(bucket="example-bucket")},
            max_download_bytes=1048576,
        )
    )
    with (
        patch.object(
            store, "_s3_client", return_value=(store.settings.s3["lake"], client)
        ),
        pytest.raises(DataError, match="Downloaded S3 objects"),
    ):
        store.query_s3("lake", ["large.csv"], "SELECT * FROM data")


def test_optional_driver_errors_are_actionable(monkeypatch: pytest.MonkeyPatch) -> None:
    statement("SELECT 1", "mysql")
    monkeypatch.setenv("MYSQL_DSN", "mysql://user:pass@localhost/test")
    store = DataStore(Settings(mysql={"main": MySQLSource(dsn_env="MYSQL_DSN")}))
    with (
        patch("data_mcp.data.importlib.import_module", side_effect=ImportError),
        pytest.raises(DataError, match="mysql.*extra"),
    ):
        store.query_mysql("main", "SELECT 1")


def test_source_config_is_strict_and_analysis_is_read_only(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unique"):
        Settings(
            files={"same": FileRoot(path=tmp_path)},
            parquet={"same": ParquetRoot(path=tmp_path)},
        )
    with pytest.raises(ValueError, match="relative"):
        S3Source(bucket="example-bucket", prefix="../outside")
    with pytest.raises(ValueError, match="allow_insecure"):
        S3Source(bucket="example-bucket", endpoint_url="http://localhost:9000")
    settings = Settings(
        access_mode="analysis",
        mysql={"db": MySQLSource(dsn_env="MYSQL_DSN")},
        mongodb={"docs": MongoSource(uri_env="MONGO_URI", database="example")},
        s3={"lake": S3Source(bucket="example-bucket", writable=True)},
    )
    sources = DataStore(settings).sources()
    assert sources["mysql"][0]["writable"] is False
    assert sources["mongodb"][0]["writable"] is False
    assert sources["s3"][0]["writable"] is False
