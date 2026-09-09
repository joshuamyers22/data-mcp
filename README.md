# Data MCP

Read/write MCP server for HDD Parquet files and local or cloud PostgreSQL databases.
Runs as a local stdio subprocess on macOS or Linux. Database connections can reach
remote hosts while Parquet access stays on the machine running the server.

Generated with `production-project-template`'s `python-cli` archetype at commit
`3d467040ba760efe9795f67f07d5a2ccf364282b`. Includes its governance, agent memory,
pinned CI actions, release/SBOM workflow, Ruff, strict Pyright, and locked dependencies.

## Setup

Requires Python 3.12+ and uv:

```sh
cd ~/Projects/data-mcp
make setup
cp config.example.toml config.toml
# Edit root paths and database credential variable names in config.toml.
# Populate DATA_MCP_LOCAL_DSN and DATA_MCP_CLOUD_DSN in the launch environment.
uv run --frozen data-mcp --config "$PWD/config.toml" --check
uv run --frozen data-mcp --config "$PWD/config.toml"
```

`--check` validates configuration and reports whether roots exist and credential
variables are set. It does not connect to databases. The last command waits for
an MCP client on stdin; stdout is protocol traffic.

Each `[parquet.NAME]` defines an absolute root and `writable` flag. Each
`[postgres.NAME]` defines a `dsn_env` variable name, `writable` flag and `sslmode`.
Both default to writable, as requested. Configuration rejects unknown fields.
Missing sources do not prevent other sources from working.

DSN shape: `postgresql://USER:PASSWORD@HOST:5432/DATABASE`. Percent-encode reserved
characters in URI components, or use libpq keyword syntax. Keep real credentials
out of committed configuration and client tool arguments. For cloud databases,
`sslmode="verify-full"` enforces certificate and hostname verification; supply
`sslrootcert=/absolute/path/to/ca.pem` in the DSN if your provider requires its CA.
`sslmode="disable"` is an explicit option for a trusted local connection.
A PostgreSQL login needs only the schema/table/sequence/function privileges the
operator intends to expose; the server never changes grants.

## MCP tools

Ana Lite integration adds an optional, versioned semantic manifest and three tools:
`get_semantic_context`, `list_metrics`, and `run_metric`. See the
[review and revised plan](docs/ANA_LITE_PLAN.md),
[15 adversarial findings](docs/reviews/ana-lite-adversarial-review.md), and
[analysis configuration](config.ana.example.toml). The normal profile keeps full
read/write capability; `access_mode="analysis"` omits and denies mutation tools.
Set `ontology_file` to an absolute promoted TOML manifest path to enable semantic tools.
It is loaded at startup and `--check` also validates it. No model SDK, paid agent,
automatic learning or UI is added by this integration.

| Tool | Operation |
|---|---|
| `list_sources` | Names, write permissions, mount/credential availability hints |
| `list_parquet` | Relative Parquet file paths and sizes under a directory |
| `describe_parquet` | Combined schema and Hive partition columns |
| `query_parquet` | DuckDB SELECT over chosen files/directories as table `data` |
| `write_parquet` | Create, append to, or explicitly replace a Parquet file |
| `list_postgres_tables` | Accessible tables and views in a named database |
| `describe_postgres` | Columns, types, nullability and defaults |
| `query_postgres` | SELECT in a read-only transaction |
| `execute_postgres` | Commit one INSERT, UPDATE or DELETE; return affected rows |

Example Parquet query arguments:

```json
{
  "root": "raw",
  "paths": ["orats/dt=2026-09-04"],
  "sql": "SELECT ticker, AVG(iv) AS mean_iv FROM data GROUP BY ticker"
}
```

Paths select files or directories recursively; overlapping selections are deduplicated.
Queries allow SELECTs, CTEs, joins between those CTEs, and common analytical functions.
File-reading/table functions, dynamic SQL, external URLs, extensions, and other
host files cannot be selected through SQL. See `src/data_mcp/sql.py` for the function
subset. Narrow to date partitions for large HDD datasets.

Example Parquet write arguments:

```json
{
  "root": "raw",
  "path": "derived/dt=2026-09-06/part-001.parquet",
  "rows_json": "[{\"ticker\":\"ABC\",\"value\":12.5}]",
  "mode": "create"
}
```

`create` refuses an existing file. `append` creates a missing file or streams the
existing file into a replacement with new rows; existing columns and types must
match, and unsafe casts fail. `replace` explicitly replaces all rows of an existing
file. A new file infers Arrow types from JSON; JSON floating-point values are not
an exact-decimal input format. Prefer new partition filenames for bulk raw data.
These tools write bounded row payloads, not arbitrary-size bulk-ingest streams.

Writes finish a same-directory temporary file before atomic publication. File locks
serialize cooperating MCP writers. Replacement and append require external ingestion
writers to coordinate; this is not an OS sandbox against a hostile local process.
Only one file is atomic, not a whole directory or multiple sources. Original backups
and database PITR remain the operator's responsibility.

PostgreSQL SQL uses the server's native dialect and configured role privileges.
Administrative SQL, multiple statements and `RETURNING` in writes are unsupported.
Failed statements roll back. Successful writes return after commit. Never retry a
write automatically: a disconnect can happen after commit and before its response.
Database functions, triggers and custom types execute under database privileges;
a SELECT restriction is not a substitute for role and function grants.

Results contain `columns`, array-valued `rows`, and `truncated`. Default query
limits are 500 rows and 256 KiB of serialized result data. Use SQL filters/aggregates
when truncated. Decimals, timestamps, UUIDs, binary values and nonfinite numbers serialize as strings.
MCP framing and SDK structured/text copies add overhead beyond the query byte budget.
These output limits do not bound the size of an individual database cell in memory.
DuckDB has a 512 MiB working-memory setting, two threads and disabled disk spill;
SQL interruption defaults to 30 seconds. PostgreSQL has statement/lock/connect
limits. HDD traversal and writes do not have hard OS-level timeouts. Two operations
run concurrently; client cancellation does not abort an already-running write.

## Connecting Mos Eisley

Mos Eisley's `feat/data-mcp-client` integration now provides explicit `mcp-list`
and `mcp-call` commands and a dispatcher for its canonical agent loop. See the
[connection guide](docs/MOS_EISLEY.md) for read/write and Ana Lite analysis setup.
Paid model and critic workflows still require their own multi-turn integration.

The server launch contract is:

```text
command: /Users/josh/Projects/data-mcp/.venv/bin/data-mcp
args: ["--config", "/Users/josh/Projects/data-mcp/config.toml"]
environment allowlist: DATA_MCP_LOCAL_DSN, DATA_MCP_CLOUD_DSN
capabilities: local file read/write, database read/write, network for cloud PostgreSQL
```

The server's write annotations are descriptive. The Mos Eisley client config
explicitly classifies each allowed tool and requires `allow_writes` for mutation
tools. Database grants and source permissions remain authoritative.

For clients using the common JSON configuration convention:

```json
{
  "mcpServers": {
    "data": {
      "command": "/Users/josh/Projects/data-mcp/.venv/bin/data-mcp",
      "args": ["--config", "/Users/josh/Projects/data-mcp/config.toml"]
    }
  }
}
```

Arrange credential environment forwarding through your client's supported mechanism.
Mount the real HDD and set real database credentials before expecting live access.

## Verification and operations

```sh
make check
make build
# Optional local integration tests: set DATA_MCP_TEST_DSN to a disposable DB.
uv run --frozen pytest -q tests/test_postgres.py
```

PostgreSQL tests create and drop a unique schema in the supplied **test** database.
CI supplies an isolated PostgreSQL service. The unit/protocol suite uses temporary
Parquet data and never reads or writes your real sources. `docs/VERIFICATION.md`
records the actual evidence and remaining deployment checks.

Operation events go to stderr using the template telemetry envelope, with operation,
outcome and duration. No SQL, rows, paths or credentials are logged by the adapter.
Review failures and duration weekly when operating; investigate write failures before
retrying. This log is diagnostic, not a durable mutation journal. The client controls
log retention and query-result retention. No cloud telemetry is shipped.

Container packaging is supplied for Linux deployment; bind-mount only the intended
root/config/CA paths and pass credential environment variables. Keep stdio attached
with `docker run -i`; there is no HTTP listener. See `REPRODUCIBILITY.md` and the
inherited release checklist before distributing or deploying.
