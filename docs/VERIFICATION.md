# Verification: data access MCP

Requirement: `PROJECT_BRIEF.md`. Material data-integrity change, implemented for
Josh Myers in a new local project. No production-data mutations during development.

Blocking rubric: (1) MCP discovery/read/write roundtrips work; (2) path escapes,
SQL statement smuggling and writes on read-only sources are rejected; (3) failed
Parquet writes preserve previous content and database errors roll back; (4) logs
exclude source rows, SQL and credentials; (5) strict typing, lint, tests and build pass.

Verification budget: three distinct passes (backend fixtures, adversarial/failure
cases plus protocol transport, full static/build gate), up to 60 minutes. Repeat
only to resolve a concrete failure or a new change. Stop on passing gates or report
missing external evidence. No paid model calls, cloud deployment or live writes.

## Evidence

The live HDD and user PostgreSQL instances are not connected; fixture evidence
does not establish production readiness. Final development evidence follows.

## Final development result — 2026-09-06

`make check build`, with `DATA_MCP_TEST_DSN` pointing at an isolated local PostgreSQL
17 Docker instance: Ruff passed, strict Pyright reported zero errors/warnings,
**41 tests passed**, and wheel/sdist builds succeeded. No real user database or raw
HDD file was touched. The test container used the official image digest
`sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675`.

| Pass | New evidence | Findings and correction |
|---|---|---|
| Backend fixtures | Parquet create/append/replace, Hive schemas, SQL aggregation | DuckDB requires allowed_paths to be set after connection creation; corrected initialization order. Canonicalized trusted configured roots for macOS /var aliases while rejecting descendant symlinks. |
| Failure/protocol | Traversal, SQL smuggling, interrupted replacement, file locks, invalid casts/JSON, nonfinite results, redacted logs, real stdio client | Corrected MCP 2 result and annotation field usage. Appends use safe schema casts, reject mismatches, and preserve original bytes on failure. |
| Database/full gate | Real PostgreSQL CRUD, rollback, timeout, bounded reads, read-only transactions, MCP database roundtrip; static checks and package build | All 41 tests passed; package builds completed. |

Self-review disposition: fixture data integrity and protocol behaviors pass the
stated development rubric. This is not independent security or release approval.
Stopped at the passing threshold. No repeated review against unchanged evidence.

Remaining external evidence: real HDD capacity/performance, PostgreSQL role/function
grants, cloud CA/hostname verification against the intended provider, backup/restore,
container base-image pin and target-host smoke test, network-backed dependency audit,
and Mos Eisley controller integration. The deployment owner resolves these before
production use. New-file publication is preferred for uncoordinated ingestion;
append/replace are not concurrency-safe against external writers ignoring locks.

Evidence lives in tests, the ADR, README and PROJECT_MEMORY.md. No raw data or
credentials are retained in this record.
