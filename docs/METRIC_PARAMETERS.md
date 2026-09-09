# Typed metric parameters

Promoted metrics can now accept declared values for date ranges and filters.
The operator owns the SQL, source, paths, parameter types and allowed bounds in
the manifest. Callers supply values to `run_metric`; they cannot replace those
parts of the definition. Invalid values fail before source access.

See [the synthetic example](../ontology/parameters.example.toml), which works with
the [Parquet case pack](ANALYTICAL_CASE_PACK.md). Copy the example outside the pinned
pack and create a separate analysis config with `ontology_file` pointing to that
copy and `parquet.fixture.path` pointing to the pack's `data` directory. The
original pack and its verification manifest can remain intact.

After starting that config, retrieve `get_semantic_context` and use its revision:

```json
{
  "name": "net_between",
  "revision": "REVISION_FROM_SEMANTIC_CONTEXT",
  "parameters": {
    "start_day": "2026-01-01",
    "end_day": "2026-02-01"
  }
}
```

The synthetic January result is 4600 cents. The result includes the submitted
parameter values alongside the fixed SQL, normalized SQL, units, timezone and
revision. Dates bind as date objects. SQL keeps placeholders; parameter values are
never inserted into the SQL text. Parameter values are result content and follow
the client's content-retention policy; operation telemetry omits them.

## Manifest contract

Each metric supports up to 16 named parameters. Names use lowercase letters,
digits and underscores, beginning with a letter. Every declared parameter is
required on every call, and every name must appear as a real SQL placeholder.
Repeated use of a placeholder is supported. Extra values, missing values and
positional placeholders fail. There are no defaults, nullable values, arrays or
object-valued parameters in this slice.

| Type | Required declaration | Accepted caller value |
|---|---|---|
| `date` | Description, inclusive `minimum` and `maximum` dates | Valid canonical `YYYY-MM-DD` string within bounds |
| `integer` | Description, inclusive signed-64-bit `minimum` and `maximum` | JSON integer within bounds; booleans and floats fail |
| `string` | Description and `max_length` from 1 to 1024 | Bounded string without NUL; optional `choices` restrict values |
| `boolean` | Description | JSON `true` or `false`; numbers and strings fail |

String `choices` may contain up to 64 distinct allowed values. Without choices,
any string satisfying the length/NUL limits is accepted, including an empty
string. Declare choices when only a finite selection is meaningful. The complete
submitted parameter object is limited to 8192 bytes using JSON serialization.
Floating-point and exact-decimal parameter contracts are deferred.

An optional `[[metrics.NAME.date_windows]]` names two distinct date parameters as
`start` and `end`, with a required `max_days` from 1 to 36600. It declares `[)`
bounds and requires `0 < end - start <= max_days`. Up to eight windows are allowed.
Reversed, empty and overly wide windows fail before execution. The SQL author
must implement the stated inclusive/exclusive comparisons and timezone semantics;
the validator does not prove the query's business meaning. A calendar-day span
is not a fixed elapsed-hour span across timezone changes. Timestamp parameters
and automatic timezone conversion are outside this contract.

## Binding and compatibility

Parquet definitions use `$name` placeholders and DuckDB's named value bindings.
PostgreSQL definitions use `%(name)s` placeholders. Only SQL AST placeholder nodes
are converted into PostgreSQL `$1`, `$2`, … slots, ordered by sorted parameter
name. The adapter passes the values separately through a raw server cursor.
Literal strings containing placeholder-like text and percent signs, and the `%`
operator, retain their meaning. Source SQL uses ordinary `%`, not Python escaping.
Database row limits, read-only transactions, timezone setup and existing SQL
restrictions continue to apply. Parameters represent values, not identifiers,
file paths, table names or SQL fragments.

Binding references: [DuckDB Python DB API](https://duckdb.org/docs/current/clients/python/dbapi)
and [Psycopg raw query cursors](https://www.psycopg.org/psycopg3/docs/advanced/cursors.html#raw-query-cursors).
The locked installed versions were exercised with actual Parquet and PostgreSQL.

Fixed-only catalogs keep the established `run_metric(name, revision)` input schema.
A catalog containing any parameterized metric advertises the additional optional
`parameters` object. A fixed metric within that catalog still takes no values.
Retrieve tools again after restarting with a changed catalog. Changes to parameter
definitions or bounds change the manifest revision; stale revisions fail.

Mos Eisley's analytical controller already uses its JSON argument wrapper, so
parameter objects pass through schema validation and remain in the SQL argument
trail. Ordinary canonical dispatch against a parameterized catalog also uses the
wrapper shown by tool discovery (`arguments_json` containing the JSON above).
The MCP wire call itself still takes the ordinary JSON object above. Tool catalog
identities change when the advertised schema changes; existing evaluation suites
must bind the current catalog before a new comparison.

This implements the typed-parameter part of Ana Lite Stage 2. It does not establish
source snapshots, complete output-schema checks or independent domain approval.
See [verification](METRIC_PARAMETERS_VERIFICATION.md).
