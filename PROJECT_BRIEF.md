# Project Brief

- Problem and affected users: Mos Eisley needs to discover, inspect, read, and write
  HDD Parquet files and local/cloud PostgreSQL data through one MCP server.
- Measurable success criteria: real MCP roundtrips exercise Parquet creation,
  SQL reads, appends, replacement, PostgreSQL reads and committed DML; failed
  writes preserve existing data; template lint, strict typing, tests and build pass.
- Explicit non-goals: remote MCP hosting, database administration/DDL, arbitrary
  host-file access, automatic credentials discovery, cross-source transactions,
  automatic retries of writes, and implementation of Mos Eisley's general client.
- Runtime/deployment environment: Python 3.12+, macOS/Linux, local stdio child of
  an MCP client. The PostgreSQL endpoint may be local or cloud hosted.
- Data classification and retention: private source data; no data or SQL in logs.
  This server creates no query history. The client owns retention of returned data.
- Availability and recovery objectives: no service SLO for this local development
  milestone; missing drives and credentials fail explicitly. Parquet publication
  is atomic per file; PostgreSQL operations commit or roll back per invocation.
  Backup/restore and production HDD throughput require operator validation.
- Capacity: default 500 returned rows, 256 KiB result data, 1 MiB row-write payload,
  10,000 selected files, 512 MiB DuckDB working memory, 30-second SQL timeout.
  Parquet writes stream existing rows but have no hard disk-I/O deadline.
- Top failure or abuse scenarios: path escape, partial file replacement, failed
  transaction, oversized result, retry of a write with an uncertain commit outcome.
- Owner: Josh Myers.
- User-directed scope: both backends permit writes; a configured source can be
  narrowed to read-only. Replacement is an explicit tool argument.
- Storage consistency: cooperating MCP writers use a per-file process lock;
  external writers must coordinate or use separate immutable partition filenames.

## Acceptance evidence

Ana Lite integration: optional promoted semantic context and fixed named SELECT
metrics share the existing adapters. Definition revisions guard execution; incomplete
metric results and changed output columns fail. An optional analytical profile
denies writes while preserving the default read/write workflow. This is not a
provider-backed agent or a source-snapshot/reproducibility guarantee. See
`docs/ANA_LITE_PLAN.md` and `docs/reviews/ana-lite-adversarial-review.md`.

See `docs/VERIFICATION.md` for the rubric and test results. Live source paths,
database grants and credentials are deployment inputs, not architecture blockers.
