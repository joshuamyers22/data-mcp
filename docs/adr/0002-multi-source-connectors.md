# Multi-source connector model

Date: 2026-09-09. Status: accepted for the 0.2 alpha.

## Context

The original server exposed only Parquet roots and PostgreSQL connections. Public
users need the same bounded MCP behavior across common local and hosted data systems
without sending connection strings through model-visible tool arguments.

## Decision

Use explicit source-type TOML sections with environment references for database
credentials. Support local Parquet, CSV, TSV, JSON, and JSON Lines through a generic
file interface; PostgreSQL and MySQL through dialect-specific SQL adapters; MongoDB
through structured JSON operations; and S3-compatible object storage through bounded
local staging into the file adapter.

Connector dependencies that are not needed for the core are package extras and are
imported only when their source is used. Hosted PostgreSQL, MySQL, MongoDB, and
S3-compatible services use the same connector as local or first-party deployments;
provider-specific query interfaces are not introduced.

The generic file tools supersede but do not remove the original Parquet tools and
configuration. One file query must select a single format. Every connector applies
the global result/write limits and analysis-mode write denial. S3 additionally
applies an aggregate staging limit; MongoDB forbids server-side JavaScript and makes
empty-filter mutations explicit.

## Consequences

The MCP surface is larger and backend semantics remain visible rather than being
forced into an unreliable lowest-common-denominator query language. Adding a new
source requires configuration, source discovery, bounded operations, MCP registration,
optional dependency metadata, tests, documentation, and an explicit authority/retry
model.

S3 queries transfer selected objects to a private temporary directory, so cost,
latency, and local capacity scale with selected bytes. Text-file append rewrites the
file and is size-limited. Cross-source queries and transactions, arbitrary MongoDB
commands, database DDL/administration, S3 append, provider IAM provisioning, and a
runtime third-party plugin loader remain out of scope.

This supersedes the two-adapter scope of
[ADR 0001](0001-local-data-mcp.md) without changing its stdio transport and
least-authority decisions.
