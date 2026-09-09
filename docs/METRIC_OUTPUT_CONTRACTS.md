# Metric output contracts

A promoted metric can declare the ordered database types and allowed nulls of its
result columns. The server checks cursor metadata before fetching rows, then checks
native scalar values before JSON conversion. A query returning text in place of an
amount fails even when its column name and printed value look unchanged. Type
checks also run for empty results and all-null columns.

Add one entry per expected column to the metric manifest:

```toml
[[metrics.net_between.output_contract]]
name = "total"
sql_type = "HUGEINT"
nullable = false
```

The [parameterized example](../ontology/parameters.example.toml) now includes this
contract and still works with the [synthetic case pack](ANALYTICAL_CASE_PACK.md).
Fetch the current semantic revision after changing or restarting the manifest.
Caller arguments cannot change the contract. Metrics without an output contract
keep their existing result shape and column-name checks.

## Supported types

`sql_type` uses the driver's canonical type spelling, including case. It does not
accept interchangeable SQL aliases. `nullable` is a required boolean. Contract
names and order must exactly match `expected_columns`; the existing 128-column
limit applies. Unsupported declared types fail at manifest load.

| Value family | Parquet / DuckDB | PostgreSQL |
|---|---|---|
| Integer | `TINYINT`, `SMALLINT`, `INTEGER`, `BIGINT`, `HUGEINT` and their `U`-prefixed unsigned forms | `int2`, `int4`, `int8` |
| Floating point | `FLOAT`, `DOUBLE` | `float4`, `float8` |
| Decimal | `DECIMAL(p,s)` | `numeric` or `numeric(p,s)` |
| Text | `VARCHAR` | `text` |
| Boolean | `BOOLEAN` | `bool` |
| Calendar date | `DATE` | `date` |
| Timestamp without zone | `TIMESTAMP` | `timestamp` |
| Timestamp with zone | `TIMESTAMP WITH TIME ZONE` | `timestamptz` |

DuckDB decimal precision and scale are part of its reported type. PostgreSQL
`numeric(p,s)` is required when the result descriptor reports both precision and
scale; use `numeric` when the result is unconstrained. For example, casting to
`numeric(12,2)` differs from an unconstrained numeric aggregate. Type widths and
reported decimal precision/scale must match exactly. This checks result metadata,
not the source column's entire schema.

PostgreSQL arrays cannot pass as their scalar element type even though the driver
registry shares a type-info object for the two OIDs. Arrays, nested values, custom
types, JSON, UUID, binary, intervals, PostgreSQL varchar/char length contracts and
other unlisted types are outside this initial opt-in contract. Ad hoc reads keep
the existing serialization behavior for those types.

## Values and evidence

Null is accepted only where `nullable=true`. Floating-point and decimal values must
be finite. Boolean/integer confusion and mismatched native Python scalar types
fail. Date and timestamp values are distinguished before serialization, including
whether a timestamp is timezone-aware. A successful empty result is allowed; this
contract imposes no minimum row count and proves no underlying NOT NULL constraint.

Exact finite decimals retain their existing string encoding; the checker never
converts them through a binary float. Date/timestamp strings also keep their existing
encoding. Successful contracted metric results include:

```json
{
  "columns": ["total"],
  "rows": [[4600]],
  "truncated": false,
  "column_types": ["HUGEINT"],
  "output_contract_verified": true
}
```

Normal metric attribution fields remain present. The marker means this server
checked the configured contract for this complete result. It is not independent
source authentication, domain correctness, unit correctness, source freshness or
an immutable snapshot assertion. Nullability is checked on observed rows. Query
casts can mask a source change; authors must still review the query and upstream
schema assumptions.

Existing byte/row limits apply, including the additional metadata. A partial metric
result fails instead of receiving the verification marker. Error diagnostics omit
rows and values. The raw read/write workflow remains available with its existing
behavior.

Mos Eisley retains the type list and marker in the original tool-response evidence.
They do not bypass its scalar-cell checks or establish trust in a user-connected
server. The optional integration checks both accepted contracted answers and a
text-for-number substitution that cannot produce a checked answer.

Implementation evidence: [verification](METRIC_OUTPUT_VERIFICATION.md). Driver
metadata is interpreted using the installed DuckDB description tuples and
[Psycopg Column metadata](https://www.psycopg.org/psycopg3/docs/api/cursors.html#the-column-class).
