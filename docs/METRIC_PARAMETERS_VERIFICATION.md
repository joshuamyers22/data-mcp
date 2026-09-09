# Metric parameter verification — 2026-09-09

## Objective and invariants

Continue the authorized data-mcp/Ana Lite integration by allowing useful date and
filter inputs to promoted definitions. Starting commits: data-mcp `4aa63ec`, Mos
Eisley `c2122b9`, clean worktrees. Material change: typed validation and bindings in
both data adapters. No paid calls, existing source access or dependency changes.
The PostgreSQL fixture uses the pinned CI PostgreSQL 17 image, a disposable schema
and localhost-only port, with test-only credentials.

| Blocking dimension | Pass threshold |
|---|---|
| Useful inputs | Actual date-window queries return distinct correct totals |
| Contract | Missing, extra, wrong-type, invalid-date, oversized and out-of-range values fail before access |
| Bindings | SQL-like text is data; repeated placeholders, literal placeholder text and percent operators work |
| Existing limits | PostgreSQL reads remain read-only and truncated row limits still apply |
| Compatibility | Fixed-only tool schema stays stable; Mos can dispatch richer schemas |
| Evidence | Values, reviewed SQL and revision survive Mos checked-answer lineage |
| Package | Static checks, relevant full gates and installed-wheel exercise pass |

Stop after the distinct evidence types pass. Further iterations require a concrete
failure. This is development verification, not independent review of domain policy.
Real-data definitions remain an owner decision; no domain was inferred from the
synthetic cases.

## Findings and corrections

- Verified SQLGlot placeholder AST shapes against the locked package. PostgreSQL
  native raw server cursors avoid rewriting percent literals or operators; tests
  bind SQL-like text and preserve literal placeholder text independently.
- The initial optional parameter object caused Mos's ordinary canonical dispatcher
  to select a JSON wrapper, breaking a fixed-metric integration call. Fixed-only
  catalogs now retain their original input schema; parameterized catalogs advertise
  the richer shape. Both paths are tested through actual MCP.
- Date declaration bounds reject implicit epoch/timestamp coercion. Runtime dates
  require canonical calendar-date strings; booleans cannot stand in for integers.
- Declared date-window metadata checks ordering and size. SQL/domain interpretation
  remains the manifest author's responsibility, explicitly documented.

## Evidence

`tests/test_parameters.py` covers real bound Parquet filters, independently fixed
answers, 18 invalid runtime inputs rejected before a mocked source call, contract
mismatches, stale revisions, date windows, choices/payload bounds, date declaration
coercion, PostgreSQL AST conversion, MCP calls and the fixed-only tool schema.
`tests/test_postgres.py` exercises real typed bindings and a repeated string value,
literal placeholder text, modulo, read-only transaction state, row truncation and
MCP dispatch. Existing case-pack and read/write regressions remain in the gate.

The Mos optional integration runs both January and February through the checked
cell controller and verifies retained parameters, SQL and semantic revision. Its
older fixed-metric and six-case Parquet integrations also pass.

Data-mcp `make check` passed Ruff, strict Pyright and all 106 tests with disposable
PostgreSQL 17. Build and locked export checks passed. A fresh installed wheel outside
the checkout passed all twelve fixed case-pack answers, the documented January and
February parameterized queries, and rejection of a reversed window. No dependency
changes were required. Mos integration is recorded in its parameter integration
verification guide; the broader Mos gate follows its updated GitHub base.
