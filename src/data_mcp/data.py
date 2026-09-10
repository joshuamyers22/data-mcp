"""Data operations. Each operation owns and closes its database connections."""

import fcntl
import importlib
import json
import os
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Timer
from typing import Any, LiteralString, cast
from urllib.parse import parse_qs, unquote, urlparse

import duckdb
import psycopg
import pyarrow as pa
import pyarrow.csv as _pcsv
import pyarrow.json as _pjson
import pyarrow.parquet as _pq
from psycopg.sql import SQL

from .config import DataFormat, FileRoot, Settings
from .output import Backend, OutputColumn, check_description, check_row
from .parameters import BoundValue, postgres_bindings
from .sql import DataError, file_query, statement

# PyArrow Parquet APIs do not ship complete type information.
pq: Any = _pq
pcsv: Any = _pcsv
pjson: Any = _pjson

FORMAT_EXTENSIONS: dict[DataFormat, frozenset[str]] = {
    "parquet": frozenset({".parquet"}),
    "csv": frozenset({".csv"}),
    "tsv": frozenset({".tsv"}),
    "json": frozenset({".json", ".jsonl", ".ndjson"}),
}


def data_format(path: Path) -> DataFormat | None:
    suffix = path.suffix.lower()
    for name, extensions in FORMAT_EXTENSIONS.items():
        if suffix in extensions:
            return name
    return None


@dataclass(frozen=True)
class Selection:
    files: list[str]
    format: DataFormat


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
            "files": [
                {
                    "name": name,
                    "available": root.path.is_dir(),
                    "writable": root.writable
                    and self.settings.access_mode == "read_write",
                    "formats": list(root.formats),
                }
                for name, root in self.settings.file_roots().items()
            ],
            # Retained so old clients can identify roots configured through the
            # original section while migrating to the generic file tools.
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
            "mysql": [
                {
                    "name": name,
                    "credential_configured": bool(os.getenv(db.dsn_env)),
                    "writable": db.writable
                    and self.settings.access_mode == "read_write",
                }
                for name, db in self.settings.mysql.items()
            ],
            "mongodb": [
                {
                    "name": name,
                    "credential_configured": bool(os.getenv(db.uri_env)),
                    "writable": db.writable
                    and self.settings.access_mode == "read_write",
                }
                for name, db in self.settings.mongodb.items()
            ],
            "s3": [
                {
                    "name": name,
                    "bucket": source.bucket,
                    "prefix": source.prefix,
                    "writable": source.writable
                    and self.settings.access_mode == "read_write",
                    "formats": list(source.formats),
                }
                for name, source in self.settings.s3.items()
            ],
        }

    def file_root(self, root: str) -> FileRoot:
        source = self.settings.file_roots().get(root)
        if source is None:
            raise DataError("Unknown file root")
        return source

    def path(self, root: str, relative: str, *, write: bool = False) -> Path:
        source = self.file_root(root)
        if write and (not source.writable or self.settings.access_mode == "analysis"):
            raise DataError("This file root is read-only")
        base = source.path
        if not base.is_dir():
            raise DataError("File root is unavailable; mount it first")
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

    def files(
        self,
        root: str,
        directory: str = ".",
        *,
        required_format: DataFormat | None = None,
    ) -> dict[str, Any]:
        folder = self.path(root, directory)
        if not folder.is_dir():
            raise DataError("Directory does not exist")
        source = self.file_root(root)
        base = source.path
        found: list[dict[str, Any]] = []
        # os.walk does not follow directory symlinks. A bounded listing is
        # deliberately not sorted globally: huge HDD trees remain streamable.
        for parent, _, names in os.walk(folder, followlinks=False):
            for name in sorted(names):
                path = Path(parent) / name
                format_name = data_format(path)
                if (
                    format_name is None
                    or format_name not in source.formats
                    or (required_format is not None and format_name != required_format)
                    or path.is_symlink()
                ):
                    continue
                relative = str(path.relative_to(base))
                if len(found) == self.settings.max_rows:
                    return {"files": found, "truncated": True}
                found.append(
                    {
                        "path": relative,
                        "format": format_name,
                        "bytes": path.stat().st_size,
                    }
                )
        return {"files": found, "truncated": False}

    def selected(
        self,
        root: str,
        paths: list[str],
        *,
        required_format: DataFormat | None = None,
    ) -> Selection:
        if not paths or len(paths) > self.settings.max_files:
            raise DataError(
                "Select at least one path, within the configured file limit"
            )
        found: set[str] = set()
        formats: set[DataFormat] = set()
        source = self.file_root(root)
        for relative in paths:
            path = self.path(root, relative)
            if path.is_dir():
                candidates = path.rglob("*")
            elif path.is_file() and data_format(path) is not None:
                candidates = [path]
            else:
                raise DataError("Selected path is not a supported file or directory")
            for candidate in candidates:
                format_name = data_format(candidate)
                if (
                    not candidate.is_file()
                    or format_name is None
                    or format_name not in source.formats
                    or (required_format is not None and format_name != required_format)
                ):
                    continue
                checked = self.path(root, str(candidate.relative_to(source.path)))
                found.add(str(checked))
                formats.add(format_name)
                if len(found) > self.settings.max_files:
                    raise DataError("Too many files; select a narrower partition")
        if not found:
            raise DataError("No supported files were found")
        if len(formats) != 1:
            raise DataError("A query must select files of one format")
        return Selection(sorted(found), formats.pop())

    @contextmanager
    def duck(
        self,
        selection: Selection,
        *,
        timezone: str | None = None,
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
        conn.execute("SET allowed_paths = ?", [selection.files])
        conn.execute("SET enable_external_access = false")
        timer = Timer(self.settings.query_timeout_seconds, conn.interrupt)
        timer.daemon = True
        timer.start()
        try:
            if timezone is not None:
                conn.execute("SET TimeZone = ?", [timezone])
            if selection.format == "parquet":
                relation = conn.from_parquet(
                    selection.files, union_by_name=True, hive_partitioning=True
                )
            elif selection.format in {"csv", "tsv"}:
                relation = conn.read_csv(
                    cast(Any, selection.files),
                    auto_detect=True,
                    delimiter="\t" if selection.format == "tsv" else ",",
                    header=True,
                    union_by_name=True,
                    hive_partitioning=True,
                )
            else:
                relation = conn.read_json(
                    cast(Any, selection.files),
                    format="auto",
                    records="auto",
                    union_by_name=True,
                    hive_partitioning=True,
                )
            relation.create_view("data")
            conn.execute("SET lock_configuration = true")
            yield conn
        finally:
            timer.cancel()
            timer.join()
            conn.close()

    def query_files(
        self,
        root: str,
        paths: list[str],
        sql: str,
        *,
        timezone: str | None = None,
        parameters: dict[str, BoundValue] | None = None,
        output_contract: tuple[OutputColumn, ...] = (),
    ) -> dict[str, Any]:
        query = file_query(sql)
        selection = self.selected(root, paths)
        with self.duck(selection, timezone=timezone) as conn:
            return result_rows(
                conn.execute(
                    f"SELECT * FROM ({query}) AS result "
                    f"LIMIT {self.settings.max_rows + 1}",
                    parameters,
                ),
                self.settings,
                output_contract=output_contract,
            )

    def describe_files(self, root: str, paths: list[str]) -> dict[str, Any]:
        selection = self.selected(root, paths)
        with self.duck(selection) as conn:
            return result_rows(conn.execute("DESCRIBE data"), self.settings)

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
        self.selected(root, paths, required_format="parquet")
        return self.query_files(
            root,
            paths,
            sql,
            timezone=timezone,
            parameters=parameters,
            output_contract=output_contract,
        )

    def describe_parquet(self, root: str, paths: list[str]) -> dict[str, Any]:
        selection = self.selected(root, paths, required_format="parquet")
        with self.duck(selection) as conn:
            return result_rows(conn.execute("DESCRIBE data"), self.settings)

    def _row_records(self, rows_json: str) -> list[dict[str, Any]]:
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
        return records

    def write_file(
        self, root: str, path: str, rows_json: str, mode: str = "create"
    ) -> dict[str, Any]:
        """Write a supported local tabular format with atomic publication."""
        target = self.path(root, path, write=True)
        format_name = data_format(target)
        source = self.file_root(root)
        if format_name is None or format_name not in source.formats:
            raise DataError("Output extension is not enabled for this file root")
        if format_name == "parquet":
            return self.write_parquet(root, path, rows_json, mode)
        if mode not in {"create", "append", "replace"}:
            raise DataError("Mode must be create, append, or replace")
        records = self._row_records(rows_json)
        target.parent.mkdir(parents=True, exist_ok=True)
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
            incoming = pa.Table.from_pylist(records)
            table = incoming
            if mode == "append" and target.exists():
                if target.stat().st_size > self.settings.max_rewrite_bytes:
                    raise DataError("Existing file exceeds the rewrite byte limit")
                if format_name in {"csv", "tsv"}:
                    existing = pcsv.read_csv(
                        target,
                        parse_options=pcsv.ParseOptions(
                            delimiter="\t" if format_name == "tsv" else ","
                        ),
                    )
                elif target.suffix.lower() == ".json":
                    try:
                        existing_rows = json.loads(target.read_text(encoding="utf-8"))
                    except (OSError, UnicodeError, ValueError):
                        raise DataError("Existing JSON file cannot be read") from None
                    if not isinstance(existing_rows, list):
                        raise DataError("Existing .json file must contain a row array")
                    existing_values = cast(list[Any], existing_rows)
                    if not all(isinstance(row, dict) for row in existing_values):
                        raise DataError("Existing .json file must contain a row array")
                    existing_records = cast(list[dict[str, Any]], existing_values)
                    existing = pa.Table.from_pylist(existing_records)
                else:
                    existing = pjson.read_json(target)
                if set(existing.schema.names) != set(incoming.schema.names):
                    raise DataError("Append columns must match the existing file")
                incoming = cast(
                    pa.Table,
                    cast(Any, incoming)
                    .select(existing.schema.names)
                    .cast(existing.schema, safe=True),
                )
                table = pa.concat_tables([existing, incoming])
            fd, name = tempfile.mkstemp(prefix=".data-mcp-", dir=target.parent)
            os.close(fd)
            temporary = Path(name)
            try:
                if format_name in {"csv", "tsv"}:
                    pcsv.write_csv(
                        table,
                        temporary,
                        write_options=pcsv.WriteOptions(
                            delimiter="\t" if format_name == "tsv" else ","
                        ),
                    )
                elif target.suffix.lower() == ".json":
                    temporary.write_text(
                        json.dumps(
                            table.to_pylist(), default=str, separators=(",", ":")
                        ),
                        encoding="utf-8",
                    )
                else:
                    with temporary.open("w", encoding="utf-8") as handle:
                        for row in table.to_pylist():
                            handle.write(
                                json.dumps(row, default=str, separators=(",", ":"))
                                + "\n"
                            )
                with temporary.open("rb") as handle:
                    os.fsync(handle.fileno())
                if mode == "create":
                    os.link(temporary, target)
                    temporary.unlink()
                else:
                    os.replace(temporary, target)
                directory_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
                return {
                    "path": path,
                    "format": format_name,
                    "mode": mode,
                    "rows_written": len(records),
                }
            finally:
                temporary.unlink(missing_ok=True)

    def write_parquet(
        self, root: str, path: str, rows_json: str, mode: str = "create"
    ) -> dict[str, Any]:
        if mode not in {"create", "append", "replace"}:
            raise DataError("Mode must be create, append, or replace")
        records = self._row_records(rows_json)
        keys = set(records[0])
        target = self.path(root, path, write=True)
        if "parquet" not in self.file_root(root).formats:
            raise DataError("Parquet is not enabled for this file root")
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
                    table = cast(
                        pa.Table,
                        cast(Any, incoming)
                        .select(existing.schema_arrow.names)
                        .cast(existing.schema_arrow, safe=True),
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

    @contextmanager
    def mysql(self, source: str, *, write: bool = False) -> Generator[Any]:
        config = self.settings.mysql.get(source)
        if config is None:
            raise DataError("Unknown MySQL source")
        if write and (not config.writable or self.settings.access_mode == "analysis"):
            raise DataError("This MySQL source is read-only")
        dsn = os.getenv(config.dsn_env)
        if not dsn:
            raise DataError("MySQL credential environment variable is unset")
        try:
            pymysql: Any = importlib.import_module("pymysql")
        except ImportError:
            raise DataError(
                "MySQL support requires the 'mysql' package extra"
            ) from None
        parsed = urlparse(dsn)
        if parsed.scheme not in {"mysql", "mysql+pymysql"} or not parsed.hostname:
            raise DataError("MySQL DSN must be a mysql:// URI")
        database = parsed.path.removeprefix("/")
        if not database:
            raise DataError("MySQL DSN must name a database")
        query = parse_qs(parsed.query, strict_parsing=False)
        ssl_ca = query.get("ssl_ca", [None])[-1]
        kwargs: dict[str, Any] = {
            "host": parsed.hostname,
            "port": parsed.port or 3306,
            "user": unquote(parsed.username or ""),
            "password": unquote(parsed.password or ""),
            "database": unquote(database),
            "connect_timeout": 5,
            "read_timeout": self.settings.query_timeout_seconds,
            "write_timeout": self.settings.query_timeout_seconds,
            "autocommit": False,
        }
        if config.tls:
            kwargs.update(
                ssl_ca=ssl_ca,
                ssl_verify_cert=True,
                ssl_verify_identity=True,
            )
        connection = pymysql.connect(**kwargs)
        try:
            yield connection
        finally:
            connection.close()

    def query_mysql(self, source: str, sql: str) -> dict[str, Any]:
        tree = statement(sql, "mysql")
        query = tree.sql(dialect="mysql", comments=False)
        with self.mysql(source) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute(query)
                result = result_rows(cursor, self.settings)
            conn.rollback()
            return result

    def execute_mysql(self, source: str, sql: str) -> dict[str, Any]:
        tree = statement(sql, "mysql", write=True)
        query = tree.sql(dialect="mysql", comments=False)
        with self.mysql(source, write=True) as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    count = cursor.rowcount
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return {"committed": True, "affected_rows": count}

    def _mongo_database(self, source: str, *, write: bool = False) -> tuple[Any, Any]:
        config = self.settings.mongodb.get(source)
        if config is None:
            raise DataError("Unknown MongoDB source")
        if write and (not config.writable or self.settings.access_mode == "analysis"):
            raise DataError("This MongoDB source is read-only")
        uri = os.getenv(config.uri_env)
        if not uri:
            raise DataError("MongoDB credential environment variable is unset")
        try:
            pymongo: Any = importlib.import_module("pymongo")
        except ImportError:
            raise DataError(
                "MongoDB support requires the 'mongodb' package extra"
            ) from None
        client = pymongo.MongoClient(
            uri,
            tls=config.tls,
            serverSelectionTimeoutMS=5000,
            timeoutMS=self.settings.query_timeout_seconds * 1000,
        )
        return client, client[config.database]

    @staticmethod
    def _collection(name: str) -> str:
        if not name or len(name) > 128 or "\x00" in name or name.startswith("system."):
            raise DataError("Invalid MongoDB collection name")
        return name

    @staticmethod
    def _mongo_value(raw: str, label: str) -> dict[str, Any]:
        try:
            value: Any = json.loads(raw, parse_constant=reject_json_constant)
        except ValueError:
            raise DataError(f"{label} must be valid JSON") from None
        if not isinstance(value, dict):
            raise DataError(f"{label} must be a JSON object")
        blocked = {"$where", "$function", "$accumulator"}

        def inspect(item: Any) -> None:
            if isinstance(item, dict):
                mapping = cast(dict[str, object], item)
                if blocked & mapping.keys():
                    raise DataError("Server-side JavaScript is unsupported")
                for nested in mapping.values():
                    inspect(nested)
            elif isinstance(item, list):
                for nested in cast(list[object], item):
                    inspect(nested)

        inspect(value)
        return cast(dict[str, Any], value)

    def list_mongodb_collections(self, source: str) -> dict[str, Any]:
        client, database = self._mongo_database(source)
        try:
            names = sorted(database.list_collection_names())
            truncated = len(names) > self.settings.max_rows
            return {
                "collections": names[: self.settings.max_rows],
                "truncated": truncated,
            }
        finally:
            client.close()

    def query_mongodb(
        self,
        source: str,
        collection: str,
        filter_json: str = "{}",
        projection_json: str | None = None,
    ) -> dict[str, Any]:
        name = self._collection(collection)
        filter_value = self._mongo_value(filter_json, "filter_json")
        projection = (
            self._mongo_value(projection_json, "projection_json")
            if projection_json is not None
            else None
        )
        client, database = self._mongo_database(source)
        try:
            cursor = (
                database[name]
                .find(filter_value, projection)
                .limit(self.settings.max_rows + 1)
            )
            result: dict[str, Any] = {"documents": [], "truncated": False}
            used = len(json.dumps(result).encode())
            for index, document in enumerate(cursor):
                normalized = json.loads(json.dumps(document, default=str))
                encoded = json.dumps(normalized, allow_nan=False)
                if (
                    index == self.settings.max_rows
                    or used + len(encoded.encode()) + 1 > self.settings.max_result_bytes
                ):
                    result["truncated"] = True
                    break
                result["documents"].append(normalized)
                used += len(encoded.encode()) + 1
            return result
        finally:
            client.close()

    def insert_mongodb(
        self, source: str, collection: str, documents_json: str
    ) -> dict[str, Any]:
        name = self._collection(collection)
        if len(documents_json.encode()) > self.settings.max_write_bytes:
            raise DataError("Write payload exceeds the configured byte limit")
        try:
            value: Any = json.loads(documents_json, parse_constant=reject_json_constant)
        except ValueError:
            raise DataError("documents_json must be valid JSON") from None
        if not isinstance(value, list) or not value:
            raise DataError("documents_json must be a nonempty array of documents")
        items = cast(list[object], value)

        def valid_document(document: object) -> bool:
            return (
                isinstance(document, dict)
                and len(cast(dict[object, object], document)) > 0
            )

        if not all(valid_document(document) for document in items):
            raise DataError("documents_json must be a nonempty array of documents")
        documents = cast(list[dict[str, Any]], items)
        client, database = self._mongo_database(source, write=True)
        try:
            result = database[name].insert_many(documents, ordered=True)
            return {
                "acknowledged": result.acknowledged,
                "inserted_count": len(result.inserted_ids),
                "inserted_ids": [str(value) for value in result.inserted_ids],
            }
        finally:
            client.close()

    def update_mongodb(
        self,
        source: str,
        collection: str,
        filter_json: str,
        update_json: str,
        *,
        many: bool = False,
        allow_all: bool = False,
    ) -> dict[str, Any]:
        name = self._collection(collection)
        filter_value = self._mongo_value(filter_json, "filter_json")
        update = self._mongo_value(update_json, "update_json")
        if not filter_value and not allow_all:
            raise DataError("An empty update filter requires allow_all=true")
        if not update or not all(key.startswith("$") for key in update):
            raise DataError("MongoDB updates must use update operators")
        client, database = self._mongo_database(source, write=True)
        try:
            action = database[name].update_many if many else database[name].update_one
            result = action(filter_value, update)
            return {
                "acknowledged": result.acknowledged,
                "matched_count": result.matched_count,
                "modified_count": result.modified_count,
            }
        finally:
            client.close()

    def delete_mongodb(
        self,
        source: str,
        collection: str,
        filter_json: str,
        *,
        many: bool = False,
        allow_all: bool = False,
    ) -> dict[str, Any]:
        name = self._collection(collection)
        filter_value = self._mongo_value(filter_json, "filter_json")
        if not filter_value and not allow_all:
            raise DataError("An empty delete filter requires allow_all=true")
        client, database = self._mongo_database(source, write=True)
        try:
            action = database[name].delete_many if many else database[name].delete_one
            result = action(filter_value)
            return {
                "acknowledged": result.acknowledged,
                "deleted_count": result.deleted_count,
            }
        finally:
            client.close()

    def _s3_client(self, source: str, *, write: bool = False) -> tuple[Any, Any]:
        config = self.settings.s3.get(source)
        if config is None:
            raise DataError("Unknown S3 source")
        if write and (not config.writable or self.settings.access_mode == "analysis"):
            raise DataError("This S3 source is read-only")
        try:
            boto3: Any = importlib.import_module("boto3")
        except ImportError:
            raise DataError("S3 support requires the 's3' package extra") from None
        client = boto3.client(
            "s3", region_name=config.region, endpoint_url=config.endpoint_url
        )
        return config, client

    @staticmethod
    def _relative_object(value: str) -> str:
        path = Path(value)
        if not value or path.is_absolute() or ".." in path.parts or "\x00" in value:
            raise DataError("Use a relative object key inside the configured prefix")
        return value.strip("/")

    @staticmethod
    def _object_key(prefix: str, relative: str) -> str:
        return "/".join(part for part in (prefix, relative) if part)

    def list_s3_objects(self, source: str, prefix: str = "") -> dict[str, Any]:
        config, client = self._s3_client(source)
        relative_prefix = self._relative_object(prefix) if prefix else ""
        full_prefix = self._object_key(config.prefix, relative_prefix)
        if full_prefix and not full_prefix.endswith("/"):
            full_prefix += "/"
        found: list[dict[str, Any]] = []
        token: str | None = None
        while len(found) <= self.settings.max_rows:
            kwargs: dict[str, Any] = {
                "Bucket": config.bucket,
                "Prefix": full_prefix,
                "MaxKeys": min(1000, self.settings.max_rows + 1 - len(found)),
            }
            if token is not None:
                kwargs["ContinuationToken"] = token
            page = client.list_objects_v2(**kwargs)
            for item in page.get("Contents", []):
                key = str(item["Key"])
                try:
                    relative = self._relative_object(
                        key.removeprefix(config.prefix).lstrip("/")
                    )
                except DataError:
                    continue
                format_name = data_format(Path(relative))
                if format_name is None or format_name not in config.formats:
                    continue
                found.append(
                    {
                        "key": relative,
                        "format": format_name,
                        "bytes": int(item["Size"]),
                    }
                )
                if len(found) > self.settings.max_rows:
                    return {"objects": found[:-1], "truncated": True}
            if not page.get("IsTruncated"):
                break
            token = page.get("NextContinuationToken")
            if token is None:
                break
        return {"objects": found, "truncated": False}

    def _selected_s3(
        self, source: str, paths: list[str]
    ) -> tuple[Any, Any, list[dict[str, Any]]]:
        if not paths or len(paths) > self.settings.max_files:
            raise DataError(
                "Select at least one object path, within the configured file limit"
            )
        config, client = self._s3_client(source)
        found: dict[str, dict[str, Any]] = {}
        for raw in paths:
            relative = self._relative_object(raw)
            format_name = data_format(Path(relative))
            if format_name is not None:
                if format_name not in config.formats:
                    raise DataError("Object format is not enabled for this S3 source")
                key = self._object_key(config.prefix, relative)
                head = client.head_object(Bucket=config.bucket, Key=key)
                found[key] = {
                    "key": key,
                    "relative": relative,
                    "format": format_name,
                    "bytes": int(head["ContentLength"]),
                }
                continue
            full_prefix = self._object_key(config.prefix, relative).rstrip("/") + "/"
            token: str | None = None
            while True:
                kwargs: dict[str, Any] = {
                    "Bucket": config.bucket,
                    "Prefix": full_prefix,
                    "MaxKeys": min(1000, self.settings.max_files + 1),
                }
                if token is not None:
                    kwargs["ContinuationToken"] = token
                page = client.list_objects_v2(**kwargs)
                for item in page.get("Contents", []):
                    key = str(item["Key"])
                    try:
                        relative_key = self._relative_object(
                            key.removeprefix(config.prefix).lstrip("/")
                        )
                    except DataError:
                        continue
                    item_format = data_format(Path(relative_key))
                    if item_format is None or item_format not in config.formats:
                        continue
                    found[key] = {
                        "key": key,
                        "relative": relative_key,
                        "format": item_format,
                        "bytes": int(item["Size"]),
                    }
                    if len(found) > self.settings.max_files:
                        raise DataError("Too many objects; select a narrower prefix")
                if not page.get("IsTruncated"):
                    break
                token = page.get("NextContinuationToken")
                if token is None:
                    break
        if not found:
            raise DataError("No supported S3 objects were found")
        formats = {item["format"] for item in found.values()}
        if len(formats) != 1:
            raise DataError("A query must select S3 objects of one format")
        total = sum(int(item["bytes"]) for item in found.values())
        if total > self.settings.max_download_bytes:
            raise DataError("Selected S3 objects exceed the download byte limit")
        return config, client, list(found.values())

    def _query_s3(
        self,
        source: str,
        paths: list[str],
        sql: str | None,
    ) -> dict[str, Any]:
        config, client, objects = self._selected_s3(source, paths)
        with tempfile.TemporaryDirectory(prefix="data-mcp-s3-") as directory:
            root = Path(directory).resolve()
            local_paths: list[str] = []
            downloaded = 0
            for item in objects:
                local_name = str(item["relative"])
                target = root / local_name
                target.parent.mkdir(parents=True, exist_ok=True)
                response = client.get_object(Bucket=config.bucket, Key=item["key"])
                body = response["Body"]
                try:
                    with target.open("wb") as handle:
                        for chunk in body.iter_chunks(chunk_size=65536):
                            downloaded += len(chunk)
                            if downloaded > self.settings.max_download_bytes:
                                raise DataError(
                                    "Downloaded S3 objects exceed the byte limit"
                                )
                            handle.write(chunk)
                finally:
                    body.close()
                local_paths.append(local_name)
            local_settings = self.settings.model_copy(
                update={
                    "files": {
                        "s3_staging": FileRoot(
                            path=root, writable=False, formats=config.formats
                        )
                    },
                    "parquet": {},
                }
            )
            local = DataStore(local_settings)
            if sql is None:
                return local.describe_files("s3_staging", local_paths)
            return local.query_files("s3_staging", local_paths, sql)

    def describe_s3(self, source: str, paths: list[str]) -> dict[str, Any]:
        return self._query_s3(source, paths, None)

    def query_s3(self, source: str, paths: list[str], sql: str) -> dict[str, Any]:
        return self._query_s3(source, paths, sql)

    def write_s3(
        self,
        source: str,
        path: str,
        rows_json: str,
        mode: str = "create",
    ) -> dict[str, Any]:
        if mode not in {"create", "replace"}:
            raise DataError(
                "S3 writes support create or replace; append is unsupported"
            )
        config, client = self._s3_client(source, write=True)
        relative = self._relative_object(path)
        format_name = data_format(Path(relative))
        if format_name is None or format_name not in config.formats:
            raise DataError("Output extension is not enabled for this S3 source")
        key = self._object_key(config.prefix, relative)
        if mode == "replace":
            client.head_object(Bucket=config.bucket, Key=key)
        with tempfile.TemporaryDirectory(prefix="data-mcp-s3-write-") as directory:
            root = Path(directory).resolve()
            local = DataStore(
                self.settings.model_copy(
                    update={
                        "files": {
                            "s3_staging": FileRoot(
                                path=root, writable=True, formats=config.formats
                            )
                        },
                        "parquet": {},
                    }
                )
            )
            local.write_file("s3_staging", Path(relative).name, rows_json)
            target = root / Path(relative).name
            with target.open("rb") as handle:
                kwargs: dict[str, Any] = {
                    "Bucket": config.bucket,
                    "Key": key,
                    "Body": handle,
                }
                if mode == "create":
                    kwargs["IfNoneMatch"] = "*"
                response = client.put_object(**kwargs)
        return {
            "key": relative,
            "format": format_name,
            "mode": mode,
            "rows_written": len(self._row_records(rows_json)),
            "etag": str(response.get("ETag", "")).strip('"') or None,
        }
