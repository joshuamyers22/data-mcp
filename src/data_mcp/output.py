"""Opt-in checks of driver result types and native scalar values before encoding."""

import math
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, StrictBool

from .config import StrictModel
from .sql import DataError

Backend = Literal["parquet", "postgres"]
Kind = Literal[
    "integer",
    "float",
    "decimal",
    "string",
    "boolean",
    "date",
    "timestamp",
    "timestamptz",
]
DUCK_TYPES: dict[str, Kind] = {
    **dict.fromkeys(
        (
            "TINYINT",
            "SMALLINT",
            "INTEGER",
            "BIGINT",
            "HUGEINT",
            "UTINYINT",
            "USMALLINT",
            "UINTEGER",
            "UBIGINT",
            "UHUGEINT",
        ),
        "integer",
    ),
    "FLOAT": "float",
    "DOUBLE": "float",
    "VARCHAR": "string",
    "BOOLEAN": "boolean",
    "DATE": "date",
    "TIMESTAMP": "timestamp",
    "TIMESTAMP WITH TIME ZONE": "timestamptz",
}
PG_TYPES: dict[str, Kind] = {
    "int2": "integer",
    "int4": "integer",
    "int8": "integer",
    "float4": "float",
    "float8": "float",
    "numeric": "decimal",
    "text": "string",
    "bool": "boolean",
    "date": "date",
    "timestamp": "timestamp",
    "timestamptz": "timestamptz",
}


class OutputColumn(StrictModel):
    name: str = Field(min_length=1, max_length=256)
    sql_type: str = Field(min_length=1, max_length=64)
    nullable: StrictBool


def kind(sql_type: str, backend: Backend) -> Kind:
    known = (DUCK_TYPES if backend == "parquet" else PG_TYPES).get(sql_type)
    if known is not None:
        return known
    if backend == "parquet":
        match = re.fullmatch(r"DECIMAL\(([0-9]+),([0-9]+)\)", sql_type)
        if match and 1 <= int(match[1]) <= 38 and 0 <= int(match[2]) <= int(match[1]):
            return "decimal"
    else:
        match = re.fullmatch(r"numeric\(([0-9]+),(-?[0-9]+)\)", sql_type)
        if match and 1 <= int(match[1]) <= 1000 and -1000 <= int(match[2]) <= 1000:
            return "decimal"
    raise DataError("Metric output SQL type is unsupported")


def check_description(
    cursor: Any, contract: tuple[OutputColumn, ...], backend: Backend
) -> list[str]:
    columns = cursor.description
    if [item[0] for item in columns] != [item.name for item in contract]:
        raise DataError("Metric output columns differ from their contract")
    actual: list[str] = []
    for column, expected in zip(columns, contract, strict=True):
        if backend == "parquet":
            name = str(column[1])
        else:
            info = cursor.adapters.types.get(column.type_code)
            # The registry also indexes array OIDs under their scalar TypeInfo.
            if info is None or info.oid != column.type_code:
                raise DataError("Metric output SQL type is unsupported")
            name = info.name
            if name == "numeric" and column.precision is not None:
                if column.scale is None:
                    raise DataError("Metric numeric result metadata is incomplete")
                name += f"({column.precision},{column.scale})"
        kind(name, backend)
        if name != expected.sql_type:
            raise DataError("Metric output SQL types changed; review its definition")
        actual.append(name)
    return actual


def check_row(
    row: tuple[Any, ...], contract: tuple[OutputColumn, ...], backend: Backend
) -> None:
    if len(row) != len(contract):
        raise DataError("Metric output row differs from its contract")
    for value, column in zip(row, contract, strict=True):
        if value is None:
            if not column.nullable:
                raise DataError("Metric output contains an unexpected null")
            continue
        family = kind(column.sql_type, backend)
        valid = False
        if family == "integer":
            valid = type(value) is int
        elif family == "float":
            valid = type(value) is float and math.isfinite(value)
        elif family == "decimal":
            valid = isinstance(value, Decimal) and value.is_finite()
        elif family == "string":
            valid = type(value) is str
        elif family == "boolean":
            valid = type(value) is bool
        elif family == "date":
            valid = type(value) is date
        elif isinstance(value, datetime):
            aware = value.tzinfo is not None and value.utcoffset() is not None
            valid = aware if family == "timestamptz" else not aware
        if not valid:
            raise DataError("Metric output contains a wrong-type or nonfinite value")
