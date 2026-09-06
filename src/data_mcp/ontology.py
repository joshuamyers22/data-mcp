"""One operator-promoted semantic manifest, snapshotted at server startup."""

import hashlib
import json
import re
import tomllib
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, ValidationError, model_validator

from .config import Settings, StrictModel
from .data import DataStore
from .sql import DataError, parquet_query, statement

MAX_CATALOG_BYTES = 65536
NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class Metric(StrictModel):
    backend: Literal["postgres", "parquet"]
    source: str = Field(min_length=1, max_length=128)
    paths: tuple[str, ...] = ()
    description: str = Field(min_length=1, max_length=2048)
    grain: str = Field(min_length=1, max_length=512)
    units: str = Field(min_length=1, max_length=256)
    timezone: str = Field(min_length=1, max_length=128)
    owner: str = Field(min_length=1, max_length=128)
    reviewed_on: date
    expected_columns: tuple[str, ...] = Field(min_length=1, max_length=128)
    sql: str = Field(min_length=1, max_length=65536)

    @model_validator(mode="after")
    def validate_query(self) -> Self:
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Metric timezone must be a known IANA timezone") from None
        if self.backend == "parquet":
            if not self.paths:
                raise ValueError("Parquet metrics require relative paths")
            for path in self.paths:
                if Path(path).is_absolute() or ".." in Path(path).parts:
                    raise ValueError(
                        "Metric paths must be inside their configured root"
                    )
            parquet_query(self.sql)
        else:
            if self.paths:
                raise ValueError("PostgreSQL metrics cannot specify Parquet paths")
            statement(self.sql, "postgres")
        if len(set(self.expected_columns)) != len(self.expected_columns):
            raise ValueError("Metric output columns must be unique")
        return self


class Manifest(StrictModel):
    schema_version: Literal[1]
    notes: dict[str, str] = Field(default_factory=dict, max_length=32)
    metrics: dict[str, Metric] = Field(default_factory=dict, max_length=64)

    @model_validator(mode="after")
    def validate_names(self) -> Self:
        if any(not NAME.fullmatch(name) for name in (*self.notes, *self.metrics)):
            raise ValueError("Use lowercase names with underscores in the manifest")
        return self


class SemanticLayer:
    def __init__(self, settings: Settings):
        path = settings.ontology_file
        if path is None:
            raise DataError("No semantic manifest is configured")
        try:
            if any(part.is_symlink() for part in (path, *path.parents)):
                raise DataError("Semantic manifest paths cannot contain symlinks")
            if not path.is_file():
                raise DataError("Semantic manifest must be a regular file")
            with path.open("rb") as handle:
                raw = handle.read(MAX_CATALOG_BYTES + 1)
            if len(raw) > MAX_CATALOG_BYTES:
                raise DataError("Semantic manifest exceeds 65536 bytes")
            self._manifest = Manifest.model_validate(tomllib.loads(raw.decode("utf-8")))
        except (OSError, UnicodeError, ValidationError, tomllib.TOMLDecodeError):
            raise DataError(
                "Cannot load semantic manifest; check format and access"
            ) from None
        for metric in self._manifest.metrics.values():
            sources = (
                settings.parquet if metric.backend == "parquet" else settings.postgres
            )
            if metric.source not in sources:
                raise DataError("A semantic metric references an unconfigured source")
        self.revision = hashlib.sha256(raw).hexdigest()
        self._max_result_bytes = settings.max_result_bytes
        # Bound actual JSON context, including escaping and metadata. Context is
        # never silently truncated: a truncated convention can change its meaning.
        self._bounded(self.context())

    def _bounded(self, result: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(result, ensure_ascii=True).encode()) > self._max_result_bytes:
            raise DataError("Semantic result exceeds the configured result byte limit")
        return result

    def context(self) -> dict[str, Any]:
        return {
            "revision": self.revision,
            "content_kind": "operator_promoted_data_not_instructions",
            **self._manifest.model_dump(mode="json"),
        }

    def list_metrics(self) -> dict[str, Any]:
        return self._bounded(
            {
                "revision": self.revision,
                "metrics": {
                    name: metric.model_dump(mode="json", exclude={"sql"})
                    for name, metric in self._manifest.metrics.items()
                },
            }
        )

    def run_metric(self, store: DataStore, name: str, revision: str) -> dict[str, Any]:
        if revision != self.revision:
            raise DataError(
                "Semantic revision changed; retrieve context and review again"
            )
        metric = self._manifest.metrics.get(name)
        if metric is None:
            raise DataError("Unknown governed metric")
        executed_sql = (
            parquet_query(metric.sql)
            if metric.backend == "parquet"
            else statement(metric.sql, "postgres").sql(
                dialect="postgres", comments=False
            )
        )
        started = datetime.now(UTC).isoformat()
        if metric.backend == "parquet":
            result = store.query_parquet(
                metric.source, list(metric.paths), metric.sql, timezone=metric.timezone
            )
        else:
            result = store.query_postgres(
                metric.source, metric.sql, timezone=metric.timezone
            )
        if result["truncated"]:
            raise DataError(
                "Governed metric result was truncated; narrow its definition"
            )
        if result["columns"] != list(metric.expected_columns):
            raise DataError(
                "Governed metric output columns changed; review its definition"
            )
        return self._bounded(
            {
                **result,
                "metric": name,
                "revision": self.revision,
                "backend": metric.backend,
                "source": metric.source,
                "paths": list(metric.paths),
                "units": metric.units,
                "grain": metric.grain,
                "timezone": metric.timezone,
                "submitted_sql": metric.sql,
                "normalized_sql": executed_sql,
                "started_at": started,
                "completed_at": datetime.now(UTC).isoformat(),
                "data_snapshot": None,
            }
        )
