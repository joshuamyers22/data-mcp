# Local stdio MCP server with two storage adapters

Date: 2026-09-06. Status: implemented development design; no release approval implied.

Generate from the production template's `python-cli` archetype at
`3d467040ba760efe9795f67f07d5a2ccf364282b`. The server is a local subprocess,
so the API-service archetype's HTTP stack is unnecessary.

Use the official MCP 2 SDK, DuckDB for Parquet SQL, PyArrow for schema-preserving
file writes, and Psycopg for PostgreSQL. DuckDB is an explicit departure from the
template's Polars default: accepting SQL with predicate/projection pushdown is the
product boundary, while no dataframe or statistics API is needed. PyArrow is the
Parquet serialization boundary; no pandas conversion is used.

The user explicitly requested read/write access to both backends. Support creates,
appends and explicit replacements of Parquet files, and transactional PostgreSQL
INSERT/UPDATE/DELETE. Prefer new partition filenames for large raw datasets;
appending to one Parquet file streams a full rewrite. This capability does not
establish an immutable published dataset contract or implement warehouse ingestion.

Operator-owned TOML lists allowed roots and database credential variable names.
SQL cannot select a connection URL or change root configuration. PostgreSQL roles
remain the authority for tables, schemas, functions and server-side capabilities.
Use TLS certificate and hostname verification for cloud connections.

No general Mos Eisley MCP client is added here. Its current repository documents
MCP support as future work. A real stdio integration test establishes interoperability
with the official client, and the README specifies the remaining Mos Eisley hook.

References: [MCP SDK](https://py.sdk.modelcontextprotocol.io/run/),
[DuckDB Parquet](https://duckdb.org/docs/current/data/parquet/overview),
[DuckDB security](https://duckdb.org/docs/current/operations_manual/securing_duckdb/overview),
[Psycopg transactions](https://www.psycopg.org/psycopg3/docs/basic/transactions.html).
