# Metric output verification — 2026-09-09

## Objective and bounds

Continue Ana Lite Stage 2 with opt-in validation of result types, nulls and finite
numeric values before serialization. Starting data-mcp commit `d782a20`; Mos
Eisley `b2c29f3`. Worktrees were clean. This is material validation work with no
provider calls, production sources or dependency changes. PostgreSQL tests use the
pinned PostgreSQL 17 image, unique disposable schemas and localhost-only access.

| Blocking dimension | Evidence / pass threshold |
|---|---|
| Type drift | Same-name integer-to-text changes fail, including empty/all-null output |
| Values | Unexpected nulls, NaN/Infinity and scalar type confusion fail |
| Precision | Decimal precision changes fail; large exact decimals survive encoding |
| Database behavior | Actual PostgreSQL metadata and bound/fixed cursors are covered |
| Compatibility | Existing uncontracted results and input schemas remain available |
| Analytical evidence | Mos retains contract metadata and rejects an otherwise matching text cell |
| Packaging | Static checks, applicable full gates and installed-wheel MCP exercise pass |

Stop after these evidence types pass; repeat only for concrete failures. The checks
are not independent domain review or a complete upstream schema/snapshot contract.

## Findings and disposition

- Driver metadata must be checked before fetching: row-only validation cannot
  identify type changes in empty or all-null results. Regressions cover both.
- Psycopg's registry resolves an array OID to the scalar type-info object. Checking
  `info.oid` against the actual column OID prevents an array from passing as int4.
- Decimal/string conversion happens only after native-type and finiteness checks.
  Exact 38-digit decimals are compared with fixed string expectations on both backends.
- Contract metadata adds bytes to the result budget. Existing truncation rejection
  remains in force, and no successful metric marker is returned for partial output.
- The marker is source-reported evidence. Mos's original response trace preserves
  it, but its controller continues to require checked scalar-cell references.

## Verification

`tests/test_output.py` exercises real DuckDB/Parquet types and values, persistent
file replacement, null and empty results, decimal drift, all three nonfinite float
forms, invalid contracts, scalar confusion, metadata-before-fetch and MCP limits.
`tests/test_postgres.py` adds fixed and parameterized cursor checks, supported scalar
families, precision drift, numeric nonfinite values, empty arrays and an actual
numeric-to-text table change under an unchanged metric revision.

All four optional Mos cross-repository tests pass with explicit disposable database
inputs. Parameterized date-window results carry the native type and verified marker.
Changing the SQL to return a string while retaining the numeric contract fails even
when the scripted proposed answer claims that exact string value.

Data-mcp `make check` passed Ruff, strict Pyright and all 145 tests with disposable
PostgreSQL 17. Build and locked-export checks passed. A fresh installed wheel outside
the checkout verified all twelve existing synthetic answers and both parameterized
example answers with their output type/verification metadata. The reversed date
window still fails. The test database container was stopped and removed afterward.
The full Mos gate is recorded in its output-contract integration guide.
