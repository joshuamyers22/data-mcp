# Data MCP Project Memory

A bounded retrieval index; verify claims against linked source and tests.
Do not store credentials, source data, query text, or routine progress here.

| Key | Durable fact | Evidence | Last verified |
|---|---|---|---|
| `template-origin` | Generated from production-project-template python-cli at 3d467040ba760efe9795f67f07d5a2ccf364282b. | docs/adr/0001-local-data-mcp.md; pyproject.toml | 2026-09-06 |
| `write-scope` | User requested writes on both backends. Parquet supports create/append/replace; PostgreSQL supports one transactional INSERT/UPDATE/DELETE without RETURNING. | PROJECT_BRIEF.md; src/data_mcp/data.py; tests/test_postgres.py | 2026-09-06 |
| `source-authority` | Operator config names roots and environment credential references. PostgreSQL roles govern server-side privileges. | src/data_mcp/config.py; config.example.toml; README.md | 2026-09-06 |
| `duckdb-lock-order` | Set allowed_paths after opening DuckDB, then disable external access and lock configuration. Passing allowed_paths in connect config fails on the locked DuckDB version. | src/data_mcp/data.py; tests/test_data.py | 2026-09-06 |
| `write-consistency` | Parquet publication is atomic per file, cooperating writers lock, and failed casts/replacement preserve the original. External writers must coordinate. No automatic write retries. | tests/test_data.py; README.md | 2026-09-06 |
| `mcp-status` | Mos Eisley integration branch supplies explicit stdio commands and a canonical agent dispatcher. Cross-repository tests cover Parquet writes, revision-bound metrics, and PostgreSQL commits across sessions. Bounded OpenAI analysis is implemented on feat/bounded-mcp-analysis; live analytical conformance remains open. | docs/MOS_EISLEY.md | 2026-09-09 |
| `remote-mcp-plan` | User-approved plan stages M11A (HTTP/token authentication) and M11B (OAuth lifecycle) extend Mos Eisley's client. M11A is implemented on feat/remote-mcp-http; M11B public-client PKCE/keychain lifecycle is implemented on feat/mcp-oauth with fixture verification. Native provider/vault deployment remains unverified. Paid analytical conversation remains separate. | docs/ANA_LITE_PLAN.md, Stage 3; linked Mos Eisley plan §13.3 | 2026-09-09 |
| `mcp-schema-status` | Mos Eisley feat/mcp-schema-compatibility adds bounded local references, local constraints and explicit JSON argument wrappers. Unsupported vocabularies and external/recursive references stay blocked; canonical provider schemas are unchanged. | docs/MOS_EISLEY.md; linked schema verification | 2026-09-09 |
| `bounded-analysis-status` | Mos Eisley feat/bounded-mcp-analysis adds read-only promoted-context conversations, whole-run OpenAI reservations, local admission limits and memory-only content retention. Fixture tests and an actual temporary Parquet conversation pass; numerical claim checking, SQL artifacts and paid analytical conformance remain open. | docs/ANA_LITE_PLAN.md, Stage 3; docs/MOS_EISLEY.md; linked analysis verification | 2026-09-09 |
| `verified-gate` | Ruff, strict Pyright, all 55 tests with disposable PostgreSQL 17, and package build passed after semantic integration. | docs/reviews/ana-lite-verification.md | 2026-09-06 |
| `ana-semantic-scope` | One explicit promoted TOML manifest is snapshotted at startup; get_semantic_context/list_metrics/run_metric provide revision-bound fixed SELECT execution. Proposals and golden files are not scanned. | src/data_mcp/ontology.py; tests/test_ontology.py; docs/ANA_LITE_PLAN.md | 2026-09-06 |
| `analysis-profile` | Optional analysis mode omits mutation tools and enforces adapter write denial; default read_write still permits authorized writes. | src/data_mcp/config.py; tests/test_ontology.py; tests/test_postgres.py | 2026-09-06 |
| `metric-timezone` | Named metric timezones are applied in both adapters; DuckDB TIMESTAMPTZ Python conversion requires the explicit pytz runtime dependency. | pyproject.toml; tests/test_ontology.py; tests/test_postgres.py | 2026-09-06 |

Open deployment inputs: live mounted root paths, named database credential environment
variables, role grants/cloud TLS validation, live analytical conformance and target
container validation. Owner: Josh Myers; review before first live use.
