# Changelog

Notable changes are recorded here using semantic versioning.

## Unreleased

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
