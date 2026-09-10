# Project Brief

- Problem and affected users: MCP clients need one controlled interface to discover,
  inspect, read, and optionally write local tabular files, SQL databases, MongoDB,
  and S3 data across local and hosted deployments.
- Measurable success criteria: MCP roundtrips exercise generic file discovery,
  creation, SQL reads, append/replacement, and database/object/document connector
  surfaces; failed writes preserve existing data; lint, strict typing, tests, export,
  and build pass.
- Explicit non-goals: remote MCP hosting, database administration/DDL, arbitrary
  host-file access, automatic credentials discovery, cross-source transactions,
  automatic retries of writes, and implementation of Mos Eisley's general client.
- Runtime/deployment environment: Python 3.12+, macOS/Linux, local stdio child of
  an MCP client. PostgreSQL, MySQL, MongoDB and S3-compatible endpoints may be local
  or hosted; their optional package extras are loaded only when used.
- Data classification and retention: private source data; no data or SQL in logs.
  This server creates no query history. The client owns retention of returned data.
- Availability and recovery objectives: no service SLO for this local development
  milestone; missing drives and credentials fail explicitly. Parquet publication
  is atomic per file; PostgreSQL operations commit or roll back per invocation.
  Backup/restore and production HDD throughput require operator validation.
- Capacity: default 500 returned rows, 256 KiB result data, 1 MiB row-write payload,
  10,000 selected files/objects, 256 MiB aggregate S3 download or text-file rewrite,
  512 MiB DuckDB working memory, and 30-second query/network timeout. File writes
  have no hard disk-I/O deadline.
- Top failure or abuse scenarios: path escape, partial file replacement, failed
  transaction, oversized result, retry of a write with an uncertain commit outcome.
- Owner: Josh Myers.
- User-directed scope: every mutable backend can be configured read-only and the
  analysis profile removes all mutation tools. Replacement and unfiltered MongoDB
  bulk changes require explicit arguments.
- Storage consistency: cooperating local-file writers use a per-file process lock;
  external writers must coordinate or use immutable partition names. S3 create uses
  a conditional put and replace is one-object publication; cross-source transactions
  and S3 append are unsupported.

## Acceptance evidence

Ana Lite integration: optional promoted semantic context and fixed named SELECT
metrics share the existing adapters. Definition revisions guard execution; incomplete
metric results and changed output columns fail. An optional analytical profile
denies writes while preserving the default read/write workflow. This is not a
provider-backed agent or a source-snapshot/reproducibility guarantee. See
`docs/ANA_LITE_PLAN.md` and `docs/reviews/ana-lite-adversarial-review.md`.

See `docs/VERIFICATION.md` for the rubric and test results. Live source paths,
database grants and credentials are deployment inputs, not architecture blockers.
