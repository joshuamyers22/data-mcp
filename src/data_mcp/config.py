"""Explicit operator-owned source configuration; credentials stay in the environment."""

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ParquetRoot(StrictModel):
    path: Path
    writable: bool = True

    @field_validator("path")
    @classmethod
    def absolute_path(cls, value: Path) -> Path:
        value = value.expanduser()
        if not value.is_absolute():
            raise ValueError("Parquet roots must be absolute paths")
        return value.resolve()


class PostgresSource(StrictModel):
    dsn_env: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    writable: bool = True
    sslmode: str = Field(default="verify-full", pattern=r"^(verify-full|disable)$")


class Settings(StrictModel):
    access_mode: Literal["read_write", "analysis"] = "read_write"
    ontology_file: Path | None = None
    parquet: dict[str, ParquetRoot] = Field(default_factory=dict)
    postgres: dict[str, PostgresSource] = Field(default_factory=dict)
    max_rows: int = Field(default=500, ge=1, le=10000)
    max_result_bytes: int = Field(default=262144, ge=1024, le=10485760)
    max_write_bytes: int = Field(default=1048576, ge=1024, le=10485760)
    max_files: int = Field(default=10000, ge=1, le=100000)
    query_timeout_seconds: int = Field(default=30, ge=1, le=300)

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
