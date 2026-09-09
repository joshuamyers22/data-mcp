# Analytical case pack verification — 2026-09-09

## Objective and authority

Continue the authorized Ana Lite/data-mcp integration with useful synthetic SQL
regressions and a Mos Eisley checked-answer roundtrip. Starting data-mcp main:
`e8ea073`; starting Mos comparison-schedule branch: `b506abd`, both clean.
Scope is material local development tooling plus a narrowly scoped SQL validator
fix. No provider calls or existing production sources are part of this milestone.

## Rubric and stopping rules

| Dimension | Blocking pass threshold |
|---|---|
| Analytical outcome | All six hand-worked answers pass over raw and promoted MCP |
| Fault sensitivity | Wrong filters, counts, null treatment, signs and empty totals differ |
| Source/label handling | Same data root; separate labels; private pinned files; writes denied |
| Validator behavior | Boolean filters work; unsafe nested functions still fail |
| Integration | Twelve actual Parquet conversations yield checked Mos cells |
| Package/maintenance | Ruff, strict Pyright, relevant tests and installed CLI pass |

Stop after these independent evidence types pass. Limit any further iteration to
concrete failures; no paid calls or database setup is required. Domain authority
is needed before treating the candidate conventions as approved source semantics.
The rubric describes this development gate, not independent acceptance approval.

## Evidence and finding disposition

| Evidence | Finding and disposition |
|---|---|
| Real SQL fixture execution | Found boolean AND rejected by the Parquet function allowlist. SQLGlot represents AND/OR as Func nodes. Permit those exact AST classes while traversing their children. |
| Seven SQL mutations | Incorrect cancellation/date filters, line counts, nullable discounts, unsigned returns and empty SUM all differ from fixed answers. |
| Five validator regressions | AND/OR/NOT query accepted; nested getenv/query calls under both connectors rejected. Existing file-access and dynamic SQL tests remain applicable. |
| Eight pack mutations | Wrong pin, changed data/labels/config, extra data files, symlink, hardlink and public permissions rejected before execution. |
| Real stdio verification | Both analysis profiles return all twelve expected complete integer cells; promoted revisions and units match. |
| Mos integration | All twelve scripted conversations pass through actual data-mcp and Mos checked scalar-cell evidence; final pinned verification passes. |

Expected values are fixed independently of query execution and explained by hand
in the guide. The implementation and oracle were authored in the same development
session, so this is not independent domain review.

## Gate results

- data-mcp `make check`: Ruff and strict Pyright passed; 73 tests passed, four
  disposable-PostgreSQL tests skipped because no DSN was supplied.
- data-mcp `make build export-check`: source distribution, wheel and locked export
  passed; no dependency changes.
- Installed data-mcp wheel: the packaged CLI created a private pack outside the
  checkout and verified all twelve answers in a fresh environment with hashed
  locked runtime dependencies.
- Mos explicit cross-repository case-pack test: passed, twelve conversations plus
  twelve verifier answers. Default Mos CI skips this optional test without the
  explicit data-mcp installation path.

No PostgreSQL implementation changed. Remaining uncertainty: real-domain
conventions, model quality, source freezing and deployment. Josh owns domain and
rollout decisions; no approval is inferred from development regression results.
