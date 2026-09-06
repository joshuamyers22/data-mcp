# Ana Lite review and integration verification

Objective: adversarially review Downloads/ana-lite-plan.md and integrate its
semantic-context/canonical-metric boundary into data-mcp. Authority: user request
of 2026-09-06; the existing read/write server remains supported.

Material change. Owner: Josh Myers. Review is by the implementing assistant with
shared context, not an independent security or product approval. Existing repository
is an uncommitted generated foundation; no user-authored changes will be discarded.

Blocking rubric:

- Findings cite concrete plan lines or repository behavior and include corrections.
- One server-owned metric definition selects one configured backend and source;
  callers cannot override its SQL, path or credential scope.
- Context/metrics have a deterministic revision; a stale execution revision fails.
- Unreviewed proposals and golden answers never enter runtime ontology context.
- Existing write access remains available; an optional analysis profile enforces
  read-only source access and omits mutation tools.
- Fixture integration, adversarial inputs, strict typing, lint and build pass.

Three evidence-changing passes: source/claim review; implementation plus boundary
tests; full project gate and documentation reconciliation. Ceiling: 60 minutes,
no paid model calls or live source mutations. Stop on passing development rubric;
identify live-provider, production-role and deployment evidence still missing.

Completed results and remaining limitations follow.

## Completed development evidence — 2026-09-06

`DATA_MCP_TEST_DSN=<disposable localhost test database> make check build`:
Ruff and formatting passed, strict Pyright reported zero errors/warnings,
**55 tests passed**, and wheel/sdist builds completed. All four PostgreSQL integration
tests ran; none were skipped in this full gate. The existing data read/write tests
remain green. No model API calls, real warehouse changes or website deployment occurred.

| Pass | New evidence | Result |
|---|---|---|
| Plan/source review | All 441 source lines, current data-mcp implementation, official PostgreSQL/Anthropic/TextQL documentation | 15 evidence-linked findings; Sonnet 5 rates confirmed, precise TextQL percentages unverified; baseline contamination and capability mismatch identified. |
| Semantic boundary | 13 tests for exact definition execution, startup snapshots, stale revisions, unsafe SQL, unknown fields/sources, excluded proposal/golden files, output columns, partial results, byte/symlink bounds, analysis enforcement, timezone and stdio transport | Passed. Timezone result conversion exposed DuckDB's missing pytz runtime dependency; added and locked it, then verified the original failing case. |
| Full regression/database | 55-test suite including real PostgreSQL metric SQL/timezone and analysis write denial, static gates and build | Passed; original Downloads plan SHA-256 unchanged; checked-in example manifest validates with two explicitly synthetic definitions. |

Implemented: optional startup semantic manifest and definition revision, three semantic
MCP tools, explicit metric source/timezone/expected columns, fail-on-truncation, and an
optional enforced analysis profile. Original read/write mode remains default.

Still pending: semantic correctness of actual business definitions, held-out provider
experiment, data-snapshot/result lineage, typed parameters/output types, production
role/function/cloud TLS verification, learning proposals/promotion, client spend/admission,
Mos Eisley MCP client, public-site deployment and bulk exports. These limitations are
called out in the revised plan and review; the passing tests do not close those stages.

Stop condition: development rubric passed. This is a contextual self-review, not
independent safety/security or release approval. Durable decisions are recorded in
PROJECT_MEMORY.md and docs/ANA_LITE_PLAN.md. Test database removed after verification.
