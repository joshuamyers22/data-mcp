"""Data operations. Each operation owns and closes its database connections."""

import fcntl
import json
import os
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from threading import Timer
from typing import Any, LiteralString, cast

import duckdb
import psycopg
import pyarrow as pa
import pyarrow.parquet as _pq
from psycopg.sql import SQL

from .config import Settings
from .output import Backend, OutputColumn, check_description, check_row
from .parameters import BoundValue, postgres_bindings
from .sql import DataError, parquet_query, statement

# PyArrow Parquet APIs do not ship complete type information.
pq: Any = _pq


def result_rows(
    cursor: Any,
    settings: Settings,
    *,
    output_contract: tuple[OutputColumn, ...] = (),
    backend: Backend = "parquet",
) -> dict[str, Any]:
    columns = [item[0] for item in cursor.description]
    result: dict[str, Any] = {"columns": columns, "rows": [], "truncated": False}
    if output_contract:
        result["column_types"] = check_description(cursor, output_contract, backend)
    used = len(json.dumps(result, default=str).encode())
    if used > settings.max_result_bytes:
        raise DataError("Column metadata exceeds the result byte limit")
    for index in range(settings.max_rows + 1):
        row = cursor.fetchone()
        if row is None:
            break
        if output_contract:
            check_row(row, output_contract, backend)
        # Decimal, timestamps, UUID and binary use strings; duplicate column
        # names remain intact because rows are arrays, not dictionaries.
        # JSON has no non-finite number literals. Preserve their identity as
        # strings, instead of failing an otherwise useful analytical result.
        normalized = json.loads(json.dumps(list(row), default=str), parse_constant=str)
        encoded = json.dumps(normalized, allow_nan=False)
        size = len(encoded.encode()) + 2
        if index == settings.max_rows or used + size > settings.max_result_bytes:
            result["truncated"] = True
            break
        result["rows"].append(json.loads(encoded))
        used += size
    return result


def reject_json_constant(value: str) -> None:
    raise DataError("JSON row input cannot contain NaN or Infinity")


class DataStore:
    def __init__(self, settings: Settings):
        self.settings = settings

    def sources(self) -> dict[str, Any]:
        return {
            "parquet": [
                {
                    "name": name,
                    "available": root.path.is_dir(),
                    "writable": root.writable
                    and self.settings.access_mode == "read_write",
                }
                for name, root in self.settings.parquet.items()
            ],
            "postgres": [
                {
                    "name": name,
                    "credential_configured": bool(os.getenv(db.dsn_env)),
                    "writable": db.writable
                    and self.settings.access_mode == "read_write",
                }
                for name, db in self.settings.postgres.items()
            ],
        }

    def path(self, root: str, relative: str, *, write: bool = False) -> Path:
        source = self.settings.parquet.get(root)
        if source is None:
            raise DataError("Unknown Parquet root")
        if write and (not source.writable or self.settings.access_mode == "analysis"):
            raise DataError("This Parquet root is read-only")
        base = source.path
        if not base.is_dir():
            raise DataError("Parquet root is unavailable; mount the drive first")
        rel = Path(relative)
        if rel.is_absolute() or ".." in rel.parts or "\x00" in relative:
            raise DataError("Use a relative path inside the configured root")
        target = base / rel
        # Reject symlinks at every component, including configured ancestors.
        for component in [target, *target.parents]:
            if component.is_symlink():
                raise DataError("Symlink paths are unsupported")
        if not target.resolve().is_relative_to(base.resolve()):
            raise DataError("Path escapes the configured root")
        return target

    def files(self, root: str, directory: str = ".") -> dict[str, Any]:
        folder = self.path(root, directory)
        if not folder.is_dir():
            raise DataError("Directory does not exist")
        base = self.settings.parquet[root].path
        found: list[dict[str, Any]] = []
        # os.walk does not follow directory symlinks. A bounded listing is
        # deliberately not sorted globally: huge HDD trees remain streamable.
        for parent, _, names in os.walk(folder, followlinks=False):
            for name in sorted(names):
                path = Path(parent) / name
                if path.suffix.lower() != ".parquet" or path.is_symlink():
                    continue
                relative = str(path.relative_to(base))
                if len(found) == self.settings.max_rows:
                    return {"files": found, "truncated": True}
                found.append({"path": relative, "bytes": path.stat().st_size})
        return {"files": found, "truncated": False}

    def selected(self, root: str, paths: list[str]) -> list[str]:
        if not paths or len(paths) > self.settings.max_files:
            raise DataError(
                "Select at least one path, within the configured file limit"
            )
        found: set[str] = set()
        for relative in paths:
            path = self.path(root, relative)
            if path.is_dir():
                candidates = path.rglob("*.parquet")
            elif path.is_file() and path.suffix.lower() == ".parquet":
                candidates = [path]
            else:
                raise DataError("Selected path is not a Parquet file or directory")
            for candidate in candidates:
                checked = self.path(
                    root, str(candidate.relative_to(self.settings.parquet[root].path))
                )
                found.add(str(checked))
                if len(found) > self.settings.max_files:
                    raise DataError("Too many files; select a narrower partition")
        if not found:
            raise DataError("No Parquet files were found")
        return sorted(found)

    @contextmanager
    def duck(
        self, files: list[str], *, timezone: str | None = None
    ) -> Generator[duckdb.DuckDBPyConnection]:
        conn = duckdb.connect(
            config={
                "autoinstall_known_extensions": False,
                "autoload_known_extensions": False,
                "python_enable_replacements": False,
                "memory_limit": "512MB",
                "threads": 2,
                "temp_directory": "",
            }
        )
        conn.execute("SET allowed_paths = ?", [files])
        conn.execute("SET enable_external_access = false")
        timer = Timer(self.settings.query_timeout_seconds, conn.interrupt)
        timer.daemon = True
        timer.start()
        try:
            if timezone is not None:
                conn.execute("SET TimeZone = ?", [timezone])
            conn.from_parquet(
                files, union_by_name=True, hive_partitioning=True
            ).create_view("data")
            conn.execute("SET lock_configuration = true")
            yield conn
        finally:
            timer.cancel()
            timer.join()
            conn.close()

    def query_parquet(
        self,
        root: str,
        paths: list[str],
        sql: str,
        *,
        timezone: str | None = None,
        parameters: dict[str, BoundValue] | None = None,
        output_contract: tuple[OutputColumn, ...] = (),
    ) -> dict[str, Any]:
        query = parquet_query(sql)
        files = self.selected(root, paths)
        with self.duck(files, timezone=timezone) as conn:
            return result_rows(
                conn.execute(
                    f"SELECT * FROM ({query}) AS result "
                    f"LIMIT {self.settings.max_rows + 1}",
                    parameters,
                ),
                self.settings,
                output_contract=output_contract,
            )

    def describe_parquet(self, root: str, paths: list[str]) -> dict[str, Any]:
        files = self.selected(root, paths)
        with self.duck(files) as conn:
            return result_rows(conn.execute("DESCRIBE data"), self.settings)

    def write_parquet(
        self, root: str, path: str, rows_json: str, mode: str = "create"
    ) -> dict[str, Any]:
        if mode not in {"create", "append", "replace"}:
            raise DataError("Mode must be create, append, or replace")
        if len(rows_json.encode()) > self.settings.max_write_bytes:
            raise DataError("Write payload exceeds the configured byte limit")
        try:
            value: Any = json.loads(rows_json, parse_constant=reject_json_constant)
        except ValueError:
            raise DataError("rows_json must be valid JSON") from None
        if not isinstance(value, list) or not value:
            raise DataError("rows_json must be a nonempty array of row objects")
        items = cast(list[Any], value)
        if not all(
            isinstance(row, dict) and len(cast(dict[str, Any], row)) > 0
            for row in items
        ):
            raise DataError("rows_json must be a nonempty array of row objects")
        records = cast(list[dict[str, Any]], items)
        keys = set(records[0])
        if any(set(row) != keys for row in records):
            raise DataError("All row objects must have the same columns")
        target = self.path(root, path, write=True)
        if target.suffix.lower() != ".parquet":
            raise DataError("Output path must end in .parquet")
        target.parent.mkdir(parents=True, exist_ok=True)
        # Persistent lock file serializes cooperating data-mcp writers across
        # processes; unlinking it would allow concurrent locks on different inodes.
        lock_path = target.with_name(f".{target.name}.lock")
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(lock_fd, "r+") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise DataError(
                    "Another writer is updating this file; retry later"
                ) from None
            self.path(root, path, write=True)
            if mode == "create" and target.exists():
                raise DataError("File exists; choose append or replace explicitly")
            if mode == "replace" and not target.is_file():
                raise DataError("Replacement target does not exist; use create")
            existing: Any = None
            if mode == "append" and target.exists():
                existing = pq.ParquetFile(target)
            temporary = None
            try:
                if existing is not None:
                    if set(existing.schema_arrow.names) != keys:
                        raise DataError("Append columns must match the existing file")
                    incoming = pa.Table.from_pylist(records)
                    table = incoming.select(existing.schema_arrow.names).cast(
                        existing.schema_arrow, safe=True
                    )
                else:
                    table = pa.Table.from_pylist(records)
                fd, name = tempfile.mkstemp(prefix=".data-mcp-", dir=target.parent)
                os.close(fd)
                temporary = Path(name)
                with pq.ParquetWriter(
                    temporary, table.schema, compression="zstd"
                ) as writer:
                    if existing is not None:
                        for batch in existing.iter_batches(batch_size=65536):
                            writer.write_batch(batch)
                    writer.write_table(table)
                with temporary.open("rb") as handle:
                    os.fsync(handle.fileno())
                if mode == "create":
                    # Atomic no-clobber publication, even for noncooperating writers.
                    os.link(temporary, target)
                    temporary.unlink()
                else:
                    os.replace(temporary, target)
                directory_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
                return {"path": path, "mode": mode, "rows_written": len(records)}
            finally:
                if existing is not None:
                    existing.close()
                if temporary is not None:
                    temporary.unlink(missing_ok=True)

    @contextmanager
    def postgres(
        self, source: str, *, write: bool = False
    ) -> Generator[psycopg.Connection[tuple[Any, ...]]]:
        db = self.settings.postgres.get(source)
        if db is None:
            raise DataError("Unknown PostgreSQL source")
        if write and (not db.writable or self.settings.access_mode == "analysis"):
            raise DataError("This PostgreSQL source is read-only")
        dsn = os.getenv(db.dsn_env)
        if not dsn:
            raise DataError("PostgreSQL credential environment variable is unset")
        timeout = self.settings.query_timeout_seconds * 1000
        with psycopg.connect(
            dsn,
            connect_timeout=5,
            sslmode=db.sslmode,
            application_name="data-mcp",
            options=f"-c statement_timeout={timeout} -c lock_timeout=5000",
        ) as conn:
            conn.read_only = not write
            yield conn

    def query_postgres(
        self,
        source: str,
        sql: str,
        *,
        timezone: str | None = None,
        parameters: dict[str, BoundValue] | None = None,
        output_contract: tuple[OutputColumn, ...] = (),
    ) -> dict[str, Any]:
        tree = statement(sql, "postgres")
        query = tree.sql(dialect="postgres", comments=False)
        with self.postgres(source) as conn:
            if timezone is not None:
                conn.execute("SELECT set_config('TimeZone', %s, true)", [timezone])
            if parameters:
                query, values = postgres_bindings(sql, parameters)
                with psycopg.RawServerCursor(conn, "data_mcp") as cursor:
                    cursor.execute(SQL(cast(LiteralString, query)), values)
                    return result_rows(
                        cursor,
                        self.settings,
                        output_contract=output_contract,
                        backend="postgres",
                    )
            with conn.cursor(name="data_mcp") as cursor:
                cursor.execute(SQL(cast(LiteralString, query)))
                return result_rows(
                    cursor,
                    self.settings,
                    output_contract=output_contract,
                    backend="postgres",
                )

    def execute_postgres(self, source: str, sql: str) -> dict[str, Any]:
        tree = statement(sql, "postgres", write=True)
        query = tree.sql(dialect="postgres", comments=False)
        with self.postgres(source, write=True) as conn:
            cursor = conn.execute(SQL(cast(LiteralString, query)), prepare=True)
            count = cursor.rowcount
        return {"committed": True, "affected_rows": count}
