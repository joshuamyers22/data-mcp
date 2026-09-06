"""Statement validation, separate from database privilege enforcement."""

import logging

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

# Parser fallback diagnostics can contain the caller's full SQL and literals.
logging.getLogger("sqlglot").disabled = True


class DataError(ValueError):
    """A diagnostic safe to show to the MCP client."""


def statement(
    sql: str, dialect: str, *, write: bool = False
) -> exp.Query | exp.Insert | exp.Update | exp.Delete:
    if not sql or len(sql.encode()) > 65536:
        raise DataError("SQL must contain between 1 and 65536 bytes")
    try:
        statements = sqlglot.parse(sql, read=dialect)
    except SqlglotError:
        raise DataError("SQL could not be parsed") from None
    if len(statements) != 1 or statements[0] is None:
        raise DataError("Exactly one SQL statement is required")
    tree = statements[0]
    if write:
        if not isinstance(tree, (exp.Insert, exp.Update, exp.Delete)):
            raise DataError("Write SQL must be INSERT, UPDATE, or DELETE")
        if tree.find(exp.Returning):
            raise DataError("RETURNING is unsupported; use a separate read query")
    else:
        if not isinstance(tree, exp.Query) or any(
            isinstance(
                node,
                (
                    exp.Insert,
                    exp.Update,
                    exp.Delete,
                    exp.Merge,
                    exp.DDL,
                    exp.Into,
                    exp.Lock,
                ),
            )
            for node in tree.walk()
        ):
            raise DataError("Read SQL must be a SELECT without writes or locks")
    return tree


def parquet_query(sql: str) -> str:
    tree = statement(sql, "duckdb")
    names = {"data"} | {cte.alias.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if (
            not isinstance(table.this, exp.Identifier)
            or table.name.lower() not in names
            or table.db
            or table.catalog
        ):
            raise DataError("Query only the selected Parquet files as table 'data'")
    # Dynamic SQL functions can bypass table validation. Only known scalar and
    # aggregate functions are accepted; no arbitrary anonymous functions/macros.
    allowed = {
        "ABS",
        "AVG",
        "CAST",
        "TRY_CAST",
        "COALESCE",
        "COUNT",
        "SUM",
        "MIN",
        "MAX",
        "ROUND",
        "FLOOR",
        "CEIL",
        "LOWER",
        "UPPER",
        "LENGTH",
        "SUBSTRING",
        "TRIM",
        "CONCAT",
        "NULLIF",
        "IF",
        "CASE",
        "EXTRACT",
        "DATE_TRUNC",
        "TIMESTAMP_TRUNC",
        "ROW_NUMBER",
        "RANK",
        "DENSE_RANK",
        "LAG",
        "LEAD",
        "FIRST_VALUE",
        "LAST_VALUE",
        "STDDEV",
        "STDDEV_SAMP",
        "STDDEV_POP",
        "VARIANCE",
        "VAR_POP",
        "VAR_SAMP",
        "PERCENTILE_CONT",
        "PERCENTILE_DISC",
        "MEDIAN",
        "POWER",
        "SQRT",
        "LOG",
        "LN",
        "EXP",
    }
    for func in tree.find_all(exp.Func):
        name = func.name.upper() if isinstance(func, exp.Anonymous) else func.sql_name()
        if name not in allowed:
            raise DataError(f"Parquet SQL function is unsupported: {name}")
    return tree.sql(dialect="duckdb", comments=False)
