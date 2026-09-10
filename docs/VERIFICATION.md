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

## Disposable service integration result — 2026-09-10

The checked-in Compose workflow brought pinned PostgreSQL 17, MySQL 8.4,
MongoDB 8.0, and Moto 5.1.13 S3-compatible services to healthy state. Running
`make integration-test` against that isolated stack completed with **162 passed**
and no skips. The stack and its disposable resources were removed afterward.

The new service-backed cases verify MySQL commit, rollback, decimal conversion,
update/delete, and transaction-enforced read-only behavior; heterogeneous MongoDB
insert/find/update/delete behavior; and S3 conditional create, collision handling,
replace, prefix selection, and CSV/Parquet/JSON Lines roundtrips. Unique table,
collection, and bucket names isolate every test.

After the integration pass, Ruff and formatting passed, strict Pyright reported
zero errors or warnings, the service-free suite reported **134 passed, 28 skipped**,
and the 0.2.0 wheel and source distribution rebuilt successfully. The all-extras
runtime export produced the same SHA-256 digest on consecutive frozen exports, and
the OSV audit reported no known vulnerabilities or adverse project statuses.
The CI workflow now provisions the four service types and runs these integration
cases during the normal quality job.

This adds real open-source driver and wire-protocol evidence, not public-cloud
provider evidence. Managed TLS/CA chains, IAM policies, MongoDB Atlas behavior,
provider-specific MySQL/PostgreSQL variants, latency, quotas, and billing remain
deployment checks. No production or user-owned data service was contacted.

## Multi-source public-package result — 2026-09-09

The 0.2 connector expansion passed Ruff, strict Pyright with zero errors/warnings,
and the full local suite: **134 passed, 23 skipped**. The skipped tests require a
disposable live PostgreSQL instance and retain the PostgreSQL 17 evidence recorded
below and in later metric verification records. No live MySQL, MongoDB, S3, or
production source was contacted.

The evidence-changing passes covered:

| Pass | Evidence | Residual limit |
|---|---|---|
| Multi-format files | Create/append/replace and DuckDB schema/query roundtrips for Parquet, CSV, TSV, JSON arrays, and JSON Lines; mixed-format and format-allowlist rejection | Large text appends rewrite the file and depend on the configured rewrite ceiling |
| Connector behavior | Isolated MySQL TLS/transaction fakes, MongoDB bounded CRUD and JavaScript/empty-filter guards, S3 conditional create/query/replace with key-boundary validation | No live provider authentication, TLS, IAM, dialect, latency, or billing evidence |
| Public artifact | Locked all-extras install, stable hash-pinned runtime export, 0.2 wheel/sdist build, installed-wheel MCP discovery in analysis mode, MIT metadata, and OSV audit with no known findings | No package or container was published; target-host container smoke remains open |

The original Parquet API remains exercised alongside the generic file API. S3
objects are streamed into a private staging directory with both declared and actual
byte enforcement; DuckDB network access and extension loading remain disabled.
Review stopped after the full gate, artifact smoke, and dependency audit passed.

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
