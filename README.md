# Data MCP

Data MCP is a local [Model Context Protocol](https://modelcontextprotocol.io/)
server for controlled access to data files, databases, document stores, and object
storage. It gives MCP clients one bounded, auditable tool surface without putting
credentials in tool arguments.

Supported sources:

- local Parquet, CSV, TSV, JSON, and JSON Lines files;
- PostgreSQL and compatible hosted services;
- MySQL and compatible hosted services;
- MongoDB, including hosted MongoDB-compatible services; and
- Amazon S3 and S3-compatible object stores containing supported tabular files.

The server runs over local stdio on macOS or Linux. Network connections originate
from the machine running the server. Data MCP is alpha software: use narrowly
privileged credentials, read-only sources where possible, and backups for writable
data.

## Install

Data MCP requires Python 3.12 or newer. Until a PyPI release is available, install
from a checkout:

```sh
git clone https://github.com/joshuamyers22/data-mcp.git
cd data-mcp
uv sync --frozen --all-extras
cp config.example.toml config.toml
uv run --frozen data-mcp --config "$PWD/config.toml" --check
```

Use only the extras you need when installing the wheel: `mysql`, `mongodb`, `s3`,
or `all`. PostgreSQL and local-file support are included in the base package.

## Configure

Configuration is strict TOML. Source names are public handles presented to the MCP
client; passwords and connection URIs stay in environment variables.

```toml
access_mode = "read_write" # Use "analysis" to disable every mutation tool.
max_rows = 500
max_result_bytes = 262144
max_write_bytes = 1048576
max_files = 10000
max_download_bytes = 268435456
max_rewrite_bytes = 268435456
query_timeout_seconds = 30

[files.local]
path = "/absolute/path/to/data"
writable = false
formats = ["parquet", "csv", "tsv", "json"]

[postgres.analytics]
dsn_env = "DATA_MCP_POSTGRES_DSN"
writable = false
sslmode = "verify-full"

[mysql.warehouse]
dsn_env = "DATA_MCP_MYSQL_DSN"
writable = false
tls = true

[mongodb.documents]
uri_env = "DATA_MCP_MONGODB_URI"
database = "analytics"
writable = false
tls = true

[s3.lake]
bucket = "example-data-bucket"
prefix = "datasets"
region = "us-east-1"
writable = false
formats = ["parquet", "csv", "json"]
```

Example credential variables:

```sh
export DATA_MCP_POSTGRES_DSN='postgresql://user:password@host:5432/database'
export DATA_MCP_MYSQL_DSN='mysql://user:password@host:3306/database'
export DATA_MCP_MONGODB_URI='mongodb+srv://user:password@cluster.example/database'
```

Percent-encode reserved URI characters. For MySQL, add `?ssl_ca=/path/to/ca.pem`
when the server certificate chains to a private CA. PostgreSQL accepts
`sslrootcert=/path/to/ca.pem` in its DSN. S3 uses boto3's standard AWS credential
chain; `region` and an optional HTTPS `endpoint_url` belong in TOML, never secret
keys. A local HTTP-compatible endpoint requires
`allow_insecure_endpoint=true` explicitly.

`--check` validates configuration and reports source/credential availability without
connecting to a database or object store. Unknown fields and relative local roots
are rejected.

## Connect an MCP client

Start Data MCP as a stdio child process. A typical MCP client configuration is:

```json
{
  "mcpServers": {
    "data": {
      "command": "/absolute/path/to/data-mcp/.venv/bin/data-mcp",
      "args": ["--config", "/absolute/path/to/data-mcp/config.toml"]
    }
  }
}
```

Forward only the credential variables used by the configured sources. The exact
environment allowlist mechanism depends on the client.

## Tools

| Source | Read tools | Write tools |
|---|---|---|
| All | `list_sources` | — |
| Local files | `list_files`, `describe_files`, `query_files` | `write_file` |
| PostgreSQL | `list_postgres_tables`, `describe_postgres`, `query_postgres` | `execute_postgres` |
| MySQL | `list_mysql_tables`, `describe_mysql`, `query_mysql` | `execute_mysql` |
| MongoDB | `list_mongodb_collections`, `query_mongodb` | `insert_mongodb`, `update_mongodb`, `delete_mongodb` |
| S3 | `list_s3_objects`, `describe_s3`, `query_s3` | `write_s3` |

Local and S3 file queries expose selected files as the DuckDB table `data`:

```json
{
  "root": "local",
  "paths": ["sales/year=2026/part-001.csv"],
  "sql": "SELECT region, SUM(revenue) FROM data GROUP BY region"
}
```

Each query must select one file format. Directories and S3 prefixes are recursive;
overlapping selections are deduplicated. Hive partition columns are inferred.
SQL can use SELECTs, CTEs, joins between those CTEs, and an allowlist of common
analytical functions. File-reading functions, extensions, external URLs, dynamic
SQL, and other host files are unavailable from query SQL.

`write_file` infers the output format from `.parquet`, `.csv`, `.tsv`, `.json`,
`.jsonl`, or `.ndjson`. It accepts a nonempty JSON array of row objects and supports
`create`, `append`, and explicit `replace`. Local publication is atomic per file and
serialized among cooperating Data MCP writers. Append validates columns and safe
type casts, but rewrites CSV, TSV, and JSON files in full; prefer immutable partitions
for large datasets. S3 writes support atomic object `create` and explicit `replace`,
not append.

PostgreSQL and MySQL query tools accept one SELECT. Their execute tools accept one
INSERT, UPDATE, or DELETE without `RETURNING`; successful calls return only after
commit. MongoDB accepts JSON filters/projections and operator-style updates.
Server-side JavaScript is rejected. Empty update/delete filters require
`allow_all=true`.

Never automatically retry a write. A connection can fail after the backend commits
but before the client receives the response.

## Limits and trust model

Query results default to 500 rows and 256 KiB of serialized data. Writes default to
1 MiB of input JSON. S3 queries first check object metadata and refuse aggregate
downloads above 256 MiB. Text-file appends refuse to rewrite an existing file above
256 MiB by default. DuckDB uses 512 MiB of working memory, two threads, no disk spill,
disabled extension loading, and a 30-second interrupt timer.
These serialization limits do not bound the in-memory size of one database cell or
MongoDB document while its driver decodes it.

Configured roots, buckets, endpoints, database roles, and environment variables are
operator-owned trust boundaries. Data MCP prevents path traversal and SQL access to
unselected local files; it is not an OS sandbox against a hostile local process.
Database functions, triggers, custom types, MongoDB operators, and S3-compatible
endpoints run with their configured backend authority. Use least-privilege accounts
and restrict the MCP client's tool allowlist.

The server logs structured operation name, outcome, and duration to stderr. It does
not log SQL, rows, paths, object keys, or credentials. Clients control retention of
returned data.

## Compatibility and semantic metrics

The original `[parquet.<name>]` configuration and `list_parquet`,
`describe_parquet`, `query_parquet`, and `write_parquet` tools remain available for
existing clients. New configurations should use `[files.<name>]` and the generic file
tools.

An optional, versioned semantic manifest adds `get_semantic_context`, `list_metrics`,
and `run_metric`. Metrics can target `backend="file"`, legacy
`backend="parquet"`, or `backend="postgres"`. See
[the semantic integration plan](docs/ANA_LITE_PLAN.md),
[metric parameters](docs/METRIC_PARAMETERS.md), and
[output contracts](docs/METRIC_OUTPUT_CONTRACTS.md).

## Development

```sh
uv sync --frozen --all-extras --dev
make check
make build
```

PostgreSQL integration tests require `DATA_MCP_TEST_DSN` to name a disposable test
database. Other connector tests use isolated fakes and never access live services.
See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and
[the verification guide](docs/VERIFICATION.md).

Data MCP is available under the [MIT License](LICENSE).
