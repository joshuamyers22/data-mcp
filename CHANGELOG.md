# Changelog

Notable changes are recorded here using semantic versioning.

## Unreleased

- Generalized local-file sources and tools across Parquet, CSV, TSV, JSON, and
  JSON Lines while retaining the original Parquet configuration and MCP tools.
- Added optional MySQL, MongoDB, and S3 connectors with bounded reads, guarded
  writes, TLS-first configuration, and environment-owned credentials.
- Added pinned disposable PostgreSQL, MySQL, MongoDB, and S3-compatible integration
  services for local contributors and CI.
- Prepared public packaging and documentation under the MIT License.
- Ana Lite adversarial review and revised MCP integration plan.
- Optional promoted semantic manifest, context/catalog tools, and revision-bound
  metric execution through Parquet or PostgreSQL with explicit metric timezones.
- Optional analysis profile enforcing read-only access while keeping the default
  read/write profile; governed metrics reject incomplete or mismatched output.

- Initial generated project foundation.
- Local stdio MCP discovery, schema inspection and bounded Parquet/PostgreSQL reads.
- Atomic Parquet creation, append and explicit replacement, with schema checks.
- Transactional PostgreSQL inserts, updates and deletes against named connections.
- Protocol, path-boundary, failure-recovery and real PostgreSQL integration tests.
