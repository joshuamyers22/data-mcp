"""Bounded metric parameter contracts and database-native value bindings."""

import json
import re
from datetime import date
from typing import Annotated, Literal, Self

from pydantic import Field, StrictInt, field_validator, model_validator
from sqlglot import exp

from .config import StrictModel
from .sql import DataError, statement

PARAMETER_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
BoundValue = str | int | bool | date


class IntegerParameter(StrictModel):
    type: Literal["integer"]
    description: str = Field(min_length=1, max_length=512)
    minimum: StrictInt = Field(ge=-(2**63), le=2**63 - 1)
    maximum: StrictInt = Field(ge=-(2**63), le=2**63 - 1)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.minimum > self.maximum:
            raise ValueError("Parameter bounds are reversed")
        return self


class DateParameter(StrictModel):
    type: Literal["date"]
    description: str = Field(min_length=1, max_length=512)
    minimum: date
    maximum: date

    @field_validator("minimum", "maximum", mode="before")
    @classmethod
    def calendar_bound(cls, value: object) -> date:
        if type(value) is date:
            return value
        if isinstance(value, str) and re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value
        ):
            return date.fromisoformat(value)
        raise ValueError("Date bounds require calendar dates, not timestamps")

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.minimum > self.maximum:
            raise ValueError("Parameter bounds are reversed")
        return self


class StringParameter(StrictModel):
    type: Literal["string"]
    description: str = Field(min_length=1, max_length=512)
    max_length: StrictInt = Field(ge=1, le=1024)
    choices: tuple[str, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def bounded_choices(self) -> Self:
        if len(set(self.choices)) != len(self.choices) or any(
            len(value) > self.max_length or "\0" in value for value in self.choices
        ):
            raise ValueError("Parameter choices are invalid")
        return self


class BooleanParameter(StrictModel):
    type: Literal["boolean"]
    description: str = Field(min_length=1, max_length=512)


Parameter = Annotated[
    IntegerParameter | DateParameter | StringParameter | BooleanParameter,
    Field(discriminator="type"),
]


class DateWindow(StrictModel):
    start: str = Field(pattern=PARAMETER_NAME.pattern)
    end: str = Field(pattern=PARAMETER_NAME.pattern)
    max_days: StrictInt = Field(ge=1, le=36600)
    bounds: Literal["[)"] = "[)"


def validate_values(
    definitions: dict[str, Parameter],
    windows: tuple[DateWindow, ...],
    values: dict[str, object],
) -> dict[str, BoundValue]:
    if set(values) != set(definitions):
        raise DataError("Supply exactly the declared metric parameters")
    try:
        if len(json.dumps(values, allow_nan=False).encode()) > 8192:
            raise ValueError
    except (TypeError, ValueError):
        raise DataError("Metric parameters exceed the JSON value limits") from None
    bound: dict[str, BoundValue] = {}
    for name, spec in definitions.items():
        value = values[name]
        if isinstance(spec, IntegerParameter):
            if type(value) is not int or not spec.minimum <= value <= spec.maximum:
                raise DataError("Metric integer parameter is invalid")
        elif isinstance(spec, BooleanParameter):
            if type(value) is not bool:
                raise DataError("Metric boolean parameter is invalid")
        elif isinstance(spec, StringParameter):
            if (
                not isinstance(value, str)
                or len(value) > spec.max_length
                or "\0" in value
                or (spec.choices and value not in spec.choices)
            ):
                raise DataError("Metric string parameter is invalid")
        else:
            if (
                not isinstance(value, str)
                or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None
            ):
                raise DataError("Metric date parameter requires YYYY-MM-DD")
            try:
                value = date.fromisoformat(value)
            except ValueError:
                raise DataError("Metric date parameter is invalid") from None
            if not spec.minimum <= value <= spec.maximum:
                raise DataError("Metric date parameter is outside its bounds")
        assert isinstance(value, (str, int, bool, date))
        bound[name] = value
    for window in windows:
        start, end = bound[window.start], bound[window.end]
        if not isinstance(start, date) or not isinstance(end, date):
            raise DataError("Date windows require date parameters")
        if not 0 < (end - start).days <= window.max_days:
            raise DataError("Metric date window is reversed, empty or too wide")
    return bound


def placeholders(sql: str, backend: Literal["file", "parquet", "postgres"]) -> set[str]:
    tree = statement(sql, "duckdb" if backend in {"file", "parquet"} else "postgres")
    if tree.find(exp.Parameter):
        raise DataError("Use declared named metric placeholders")
    names: set[str] = set()
    for node in tree.find_all(exp.Placeholder):
        if not PARAMETER_NAME.fullmatch(node.name):
            raise DataError("Use declared named metric placeholders")
        names.add(node.name)
    return names


def postgres_bindings(
    sql: str, values: dict[str, BoundValue]
) -> tuple[str, list[BoundValue]]:
    """Convert only AST placeholders to $N; literals and percent operators survive."""
    if placeholders(sql, "postgres") != set(values):
        raise DataError("SQL placeholders differ from metric parameters")
    names = sorted(values)
    tree = statement(sql, "postgres")
    for node in tuple(tree.find_all(exp.Placeholder)):
        node.replace(exp.Parameter(this=exp.Literal.number(names.index(node.name) + 1)))
    return tree.sql(dialect="postgres", comments=False), [
        values[name] for name in names
    ]
