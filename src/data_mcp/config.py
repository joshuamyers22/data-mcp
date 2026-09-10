"""Explicit operator-owned source configuration; credentials stay in the environment."""

import tomllib
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DataFormat = Literal["parquet", "csv", "tsv", "json"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FileRoot(StrictModel):
    path: Path
    writable: bool = True
    formats: tuple[DataFormat, ...] = ("parquet", "csv", "tsv", "json")

    @field_validator("path")
    @classmethod
    def absolute_path(cls, value: Path) -> Path:
        value = value.expanduser()
        if not value.is_absolute():
            raise ValueError("File roots must be absolute paths")
        return value.resolve()

    @field_validator("formats")
    @classmethod
    def valid_formats(cls, value: tuple[DataFormat, ...]) -> tuple[DataFormat, ...]:
        if not value:
            raise ValueError("File roots must allow at least one format")
        if len(value) != len(set(value)):
            raise ValueError("File root formats must be unique")
        return value


class ParquetRoot(FileRoot):
    """Compatibility configuration for the legacy ``[parquet.*]`` section."""

    formats: tuple[DataFormat, ...] = ("parquet",)

    @field_validator("formats")
    @classmethod
    def parquet_only(cls, value: tuple[DataFormat, ...]) -> tuple[DataFormat, ...]:
        if value != ("parquet",):
            raise ValueError("Legacy Parquet roots only support the parquet format")
        return value


class PostgresSource(StrictModel):
    dsn_env: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    writable: bool = True
    sslmode: str = Field(default="verify-full", pattern=r"^(verify-full|disable)$")


class MySQLSource(StrictModel):
    dsn_env: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    writable: bool = True
    tls: bool = True


class MongoSource(StrictModel):
    uri_env: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    database: str = Field(min_length=1, max_length=128)
    writable: bool = True
    tls: bool = True


class S3Source(StrictModel):
    bucket: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
    prefix: str = ""
    region: str | None = None
    endpoint_url: str | None = None
    allow_insecure_endpoint: bool = False
    writable: bool = False
    formats: tuple[DataFormat, ...] = ("parquet", "csv", "tsv", "json")

    @field_validator("prefix")
    @classmethod
    def relative_prefix(cls, value: str) -> str:
        if value.startswith("/") or ".." in Path(value).parts or "\x00" in value:
            raise ValueError("S3 prefixes must be relative and cannot contain '..'")
        return value.strip("/")

    @field_validator("formats")
    @classmethod
    def valid_formats(cls, value: tuple[DataFormat, ...]) -> tuple[DataFormat, ...]:
        if not value or len(value) != len(set(value)):
            raise ValueError("S3 formats must be nonempty and unique")
        return value

    @model_validator(mode="after")
    def secure_endpoint(self) -> Self:
        if self.endpoint_url is None:
            return self
        parsed = urlparse(self.endpoint_url)
        if not parsed.hostname or parsed.scheme not in {"http", "https"}:
            raise ValueError("S3 endpoint_url must be an HTTP(S) URL")
        if parsed.scheme != "https" and not self.allow_insecure_endpoint:
            raise ValueError("HTTP S3 endpoints require allow_insecure_endpoint=true")
        return self


class Settings(StrictModel):
    access_mode: Literal["read_write", "analysis"] = "read_write"
    ontology_file: Path | None = None
    files: dict[str, FileRoot] = Field(default_factory=dict)
    parquet: dict[str, ParquetRoot] = Field(default_factory=dict)
    postgres: dict[str, PostgresSource] = Field(default_factory=dict)
    mysql: dict[str, MySQLSource] = Field(default_factory=dict)
    mongodb: dict[str, MongoSource] = Field(default_factory=dict)
    s3: dict[str, S3Source] = Field(default_factory=dict)
    max_rows: int = Field(default=500, ge=1, le=10000)
    max_result_bytes: int = Field(default=262144, ge=1024, le=10485760)
    max_write_bytes: int = Field(default=1048576, ge=1024, le=10485760)
    max_files: int = Field(default=10000, ge=1, le=100000)
    max_download_bytes: int = Field(default=268435456, ge=1048576, le=10737418240)
    max_rewrite_bytes: int = Field(default=268435456, ge=1048576, le=10737418240)
    query_timeout_seconds: int = Field(default=30, ge=1, le=300)

    @model_validator(mode="after")
    def unique_source_names(self) -> Self:
        if self.files.keys() & self.parquet.keys():
            raise ValueError("Source names must be unique across files and parquet")
        return self

    def file_roots(self) -> dict[str, FileRoot]:
        """Return generic and legacy roots through one internal interface."""
        return {**self.files, **self.parquet}

    @field_validator("ontology_file")
    @classmethod
    def absolute_ontology(cls, value: Path | None) -> Path | None:
        if value is None:
            return None
        value = value.expanduser()
        if not value.is_absolute():
            raise ValueError("ontology_file must be an absolute path")
        return value

    @classmethod
    def load(cls, path: Path) -> "Settings":
        with path.open("rb") as handle:
            return cls.model_validate(tomllib.load(handle))
