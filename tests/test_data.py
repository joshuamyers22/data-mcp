import json
from pathlib import Path
from unittest.mock import patch

import pyarrow as pa
import pytest

from data_mcp.config import FileRoot, ParquetRoot, Settings
from data_mcp.data import DataStore
from data_mcp.sql import DataError, parquet_query, statement


@pytest.fixture
def store(tmp_path: Path) -> DataStore:
    return DataStore(Settings(parquet={"raw": ParquetRoot(path=tmp_path)}))


def test_create_append_replace_and_schema(store: DataStore) -> None:
    store.write_parquet("raw", "dt=2026-09-06/a.parquet", '[{"id":1,"value":2}]')
    store.write_parquet(
        "raw", "dt=2026-09-06/a.parquet", '[{"id":2,"value":4}]', "append"
    )
    result = store.query_parquet(
        "raw", ["."], "SELECT dt, sum(value) FROM data GROUP BY dt"
    )
    assert result["rows"] == [["2026-09-06", 6]]
    assert not result["truncated"]
    schema = store.describe_parquet("raw", ["."])
    assert {"id", "value", "dt"} == {row[0] for row in schema["rows"]}
    store.write_parquet(
        "raw", "dt=2026-09-06/a.parquet", '[{"id":3,"value":9}]', "replace"
    )
    assert store.query_parquet("raw", ["."], "SELECT id FROM data")["rows"] == [[3]]
    assert len(store.files("raw")["files"]) == 1


@pytest.mark.parametrize("extension", ["csv", "tsv", "json", "jsonl"])
def test_generic_file_formats(tmp_path: Path, extension: str) -> None:
    store = DataStore(Settings(files={"local": FileRoot(path=tmp_path)}))
    path = f"rows.{extension}"
    created = store.write_file("local", path, '[{"id":1,"label":"a"}]')
    assert created["format"] == ("json" if extension.startswith("json") else extension)
    store.write_file("local", path, '[{"id":2,"label":"b"}]', "append")
    result = store.query_files(
        "local", [path], "SELECT sum(id), count(label) FROM data"
    )
    assert result["rows"] == [[3, 2]]
    schema = store.describe_files("local", [path])
    assert {row[0] for row in schema["rows"]} == {"id", "label"}
    store.write_file("local", path, '[{"id":3,"label":"c"}]', "replace")
    assert store.query_files("local", [path], "SELECT id FROM data")["rows"] == [[3]]


def test_file_format_allowlist_and_mixed_query(tmp_path: Path) -> None:
    store = DataStore(
        Settings(files={"local": FileRoot(path=tmp_path, formats=("csv", "json"))})
    )
    store.write_file("local", "a.csv", '[{"id":1}]')
    store.write_file("local", "b.json", '[{"id":2}]')
    with pytest.raises(DataError, match="one format"):
        store.query_files("local", ["a.csv", "b.json"], "SELECT * FROM data")
    with pytest.raises(DataError, match="not enabled"):
        store.write_file("local", "c.parquet", '[{"id":3}]')
    assert {item["format"] for item in store.files("local")["files"]} == {
        "csv",
        "json",
    }


def test_json_append_rejects_existing_non_object_rows(tmp_path: Path) -> None:
    store = DataStore(Settings(files={"local": FileRoot(path=tmp_path)}))
    target = tmp_path / "rows.json"
    target.write_text("[1]", encoding="utf-8")

    with pytest.raises(DataError, match="row array"):
        store.write_file("local", target.name, '[{"id":2}]', "append")

    assert target.read_text(encoding="utf-8") == "[1]"


def test_failed_create_and_append_preserve_file(store: DataStore) -> None:
    store.write_parquet("raw", "a.parquet", '[{"id":1}]')
    target = store.path("raw", "a.parquet")
    before = target.read_bytes()
    with pytest.raises(DataError, match="exists"):
        store.write_parquet("raw", "a.parquet", '[{"id":2}]')
    with pytest.raises(DataError, match="columns"):
        store.write_parquet("raw", "a.parquet", '[{"wrong":2}]', "append")
    with pytest.raises(pa.ArrowInvalid):
        store.write_parquet("raw", "a.parquet", '[{"id":1.5}]', "append")
    assert target.read_bytes() == before


def test_atomic_replacement_failure_preserves_original(store: DataStore) -> None:
    store.write_parquet("raw", "a.parquet", '[{"id":1}]')
    target = store.path("raw", "a.parquet")
    before = target.read_bytes()
    with (
        patch("data_mcp.data.os.replace", side_effect=OSError("injected failure")),
        pytest.raises(OSError),
    ):
        store.write_parquet("raw", "a.parquet", '[{"id":2}]', "replace")
    assert target.read_bytes() == before
    assert not list(target.parent.glob(".data-mcp-*"))


@pytest.mark.parametrize("path", ["../escape.parquet", "/tmp/escape.parquet"])
def test_path_escape_rejected(store: DataStore, path: str) -> None:
    with pytest.raises(DataError):
        store.write_parquet("raw", path, '[{"id":1}]')


def test_symlink_rejected(store: DataStore, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(DataError, match="Symlink"):
        store.write_parquet("raw", "link/a.parquet", '[{"id":1}]')


def test_readonly_and_unavailable_roots(tmp_path: Path) -> None:
    store = DataStore(
        Settings(
            parquet={
                "ro": ParquetRoot(path=tmp_path, writable=False),
                "offline": ParquetRoot(path=tmp_path / "missing"),
            }
        )
    )
    with pytest.raises(DataError, match="read-only"):
        store.write_parquet("ro", "a.parquet", '[{"id":1}]')
    with pytest.raises(DataError, match="mount"):
        store.files("offline")
    assert not (tmp_path / "missing").exists()


def test_result_limits_and_duplicate_columns(tmp_path: Path) -> None:
    store = DataStore(Settings(parquet={"raw": ParquetRoot(path=tmp_path)}, max_rows=2))
    store.write_parquet("raw", "a.parquet", '[{"id":1},{"id":2},{"id":3}]')
    result = store.query_parquet(
        "raw", ["a.parquet"], "SELECT id, id FROM data ORDER BY id"
    )
    assert len(result["columns"]) == 2
    assert result["rows"] == [[1, 1], [2, 2]]
    assert result["truncated"]
    store.write_parquet("raw", "b.parquet", json.dumps([{"text": "x" * 300000}]))
    result = store.query_parquet("raw", ["b.parquet"], "SELECT * FROM data")
    assert result["rows"] == []
    assert result["truncated"]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM '/etc/passwd'",
        "SELECT * FROM query('SELECT 1')",
        "SELECT getenv('HOME') FROM data",
        "SELECT * FROM data; DELETE FROM data",
        "COPY data TO '/tmp/escape.parquet'",
        "SELECT * INTO other FROM data",
        "SELECT * FROM information_schema.tables",
    ],
)
def test_unsafe_parquet_sql_rejected(sql: str) -> None:
    with pytest.raises(DataError):
        parquet_query(sql)


def test_cte_aggregate_supported(store: DataStore) -> None:
    store.write_parquet("raw", "a.parquet", '[{"id":1},{"id":2}]')
    result = store.query_parquet(
        "raw",
        ["."],
        "WITH x AS (SELECT id FROM data WHERE id > 1) SELECT COUNT(*) FROM x",
    )
    assert result["rows"] == [[1]]


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM t",
        "SELECT 1; SELECT 2",
        "WITH gone AS (DELETE FROM t RETURNING *) SELECT * FROM gone",
        "SELECT * FROM t FOR UPDATE",
    ],
)
def test_read_sql_cannot_write(sql: str) -> None:
    with pytest.raises(DataError):
        statement(sql, "postgres")


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE t",
        "UPDATE t SET id=1 RETURNING *",
        "UPDATE t SET id=1; COMMIT",
        "COPY t FROM STDIN",
    ],
)
def test_write_sql_is_one_dml(sql: str) -> None:
    with pytest.raises(DataError):
        statement(sql, "postgres", write=True)


@pytest.mark.parametrize(
    "payload", ["[]", "{}", "[1]", "[{}]", '[{"id":NaN}]', '[{"id":1},{"other":2}]']
)
def test_invalid_row_payload_does_not_create_file(
    store: DataStore, payload: str
) -> None:
    with pytest.raises(DataError):
        store.write_parquet("raw", "a.parquet", payload)
    assert not store.path("raw", "a.parquet").exists()


def test_nonfinite_query_results_remain_valid_json(store: DataStore) -> None:
    store.write_parquet("raw", "a.parquet", '[{"id":1}]')
    result = store.query_parquet(
        "raw", ["a.parquet"], "SELECT CAST('NaN' AS DOUBLE) FROM data"
    )
    assert result["rows"] == [["NaN"]]
    json.dumps(result, allow_nan=False)


def test_busy_file_lock_rejects_write(store: DataStore) -> None:
    import fcntl

    store.write_parquet("raw", "a.parquet", '[{"id":1}]')
    lock_path = store.path("raw", ".a.parquet.lock")
    with lock_path.open("r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(DataError, match="Another writer"):
            store.write_parquet("raw", "a.parquet", '[{"id":2}]', "append")
    assert store.query_parquet("raw", ["a.parquet"], "SELECT id FROM data")["rows"] == [
        [1]
    ]
