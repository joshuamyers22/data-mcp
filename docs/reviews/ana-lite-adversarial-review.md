# Ana Lite: adversarial plan review

Reviewed 2026-09-06 against the initial private design draft (441 lines;
SHA-256 `fdfa44b59ca33a18bc65319dbaba79cd7413abf6f616e08fd0d98e40475177d5`) and
`src/data_mcp/{config,data,server,sql}.py`. Source line references below refer to
that original, unchanged plan. Review follows the production template's adversarial
review rubric. Reviewer is the implementing assistant, not an independent approver.

**Verdict: revise before using the plan as an implementation or evaluation spec.**
The small, hand-maintained semantic layer and deterministic metric panels are useful
starting points. The plan does not yet support its claims of reproducibility,
comparative improvement, bounded spending or safety on a public website. Build the
semantic layer on the existing MCP adapters, then evaluate the agent separately.

Severity: High blocks the affected milestone; Medium is a necessary correction
before the affected capability ships; Low is a potential simplification. These are
plan findings, not claims that an unbuilt Ana implementation has been exploited.

## Findings, ordered by severity

### A01 — High: the evaluation trains on its own test set

**Location:** lines 55–75, 172–189, 241–247. Five questions drive ontology edits and
prompt tuning, then the same questions measure the supposed gain. Choosing a harder
schema after the baseline succeeds further selects for baseline failure. Stage 0's
manual chat and stage 6's agent may also differ in tools, model, sampling and budget.

**Failure:** an overfit layer appears better without evidence it helps new questions.
Five curated cases are a smoke test, not a reliable effect estimate. Clarification
is not a numerical mismatch and needs its own scoring rule.

**Necessary change:** declare the target schema before comparison; separate development
examples from unseen question families, keep golden expected answers inaccessible to
runtime context, freeze ontology/prompt/model/tool budgets before the holdout, and run
all arms through the same runner. Compare paired cases against one data snapshot,
including failures, abstentions, total tokens/cost, latency and maintenance time.

**Acceptance:** changing training conventions cannot change holdout labels; all arms
have the same opportunities/budgets; an ambiguous holdout requires the declared
clarification rather than an invented table. Report per-case evidence and uncertainty;
do not claim statistical improvement from five successes. Scope: medium.

### A02 — High: prompt injection is not limited to a weird answer

**Location:** lines 29, 367–375; current MCP `write_parquet`/`execute_postgres` tools.
Read permission can expose sensitive records to a provider or into an answer; SQL
functions and costly reads add consequences even without table DML. Connecting Ana
to this server's default write tools also enables mutation under its credentials.
A shared public-site password does not eliminate external attackers or stolen sessions.

**Necessary change:** separate the analysis tool profile from the authorized writer
workflow. Give analysis a dedicated database role, approved sources and read-only
Parquet mounts/flags; omit mutation tools and enforce denial in the adapter too.
Data/ontology text is untrusted content, not instructions or capability grants.
Keep the existing read/write profile for explicit data-management work.

**Acceptance:** a fixture cell asking to replace raw data or run a DELETE cannot
obtain a mutation capability in analysis; prompts cannot choose DSNs or arbitrary
roots; production role/function privileges and provider data transfer are reviewed.
Scope: medium. The integration adds the local profile; it cannot establish a hosted
client's prompt-injection resistance or correct production database grants.

### A03 — High: source snapshots and result provenance are missing

**Location:** lines 64–66, 172–175, 203–205, 293–295. A hand-recorded number and a
SQL trail do not identify the data version, cutoff, timezone, execution settings,
ontology revision or even which result supports the final claim. Live ingestion can
change a correct metric between notebook and dashboard executions.

**Necessary change:** record run ID, selected source, metric/ontology revision,
submitted and executed SQL, result identity, truncation, execution time and a defined
as-of contract. Use immutable fixture partitions or an explicitly fixed database
snapshot for comparisons. Tie each final answer/chart to a particular result ID.

**Acceptance:** baseline and treatment read identical fixture data; stale ontology
revision execution fails; every displayed value maps to its generating result.
Do not describe a definition hash as a data snapshot or proof of semantic correctness.
Scope: medium; the integration supplies definition revision, not full data lineage.

### A04 — High: canonical SQL in a prompt is not governed execution

**Location:** lines 146–149, 175–181, 284–295. A prompt urging the model to reuse SQL
still permits subtle rewrites. Panels and agent answers can disagree on parameters,
time cutoff, data state or model interpretation even when a metric has one name.

**Necessary change:** implement `list_metrics` and `run_metric(name, revision)` with
server-owned source/dialect/SQL. Clients provide no SQL override for that tool.
Clearly label free-form `query_*` results as ad hoc. Add typed bound parameters
before metrics need user-supplied dates/filters; parameterization is not a DSL project.

**Acceptance:** both consumers call the same metric execution; a changed definition
invalidates the old revision; injection cannot become metric SQL through a name or
parameter. Scope: small for fixed definitions; medium for typed parameters.

### A05 — High: spend is counted after admission rather than reserved before it

**Location:** lines 203–205, 318–328, 372, 380–387. End-of-run logging and a
per-session daily count cannot prevent concurrent requests from overspending. Session
rotation bypasses session-only ceilings. No maximum tool turns, output tokens,
wall-clock budget, queue size or reservation for an uncertain provider outcome exists.
Raising a reverse-proxy timeout does not cancel work already running.

**Necessary change:** the client/controller owns account/user-scoped atomic budget
admission, model/output/tool limits, cancellation and bounded queues from the first
paid run. Reserve worst-case remaining cost before calls and reconcile usage afterward;
keep uncertain reservations until resolved. A provider console cap is a backstop.
Do not assume Mos Eisley's one-prompt spending ledger already governs a new Anthropic
multi-turn loop—it currently does not.

**Acceptance:** two simultaneous requests cannot over-admit the remaining budget;
request disconnect and provider timeout produce a known terminal/uncertain state;
reloading the browser cannot reset allowance. Scope: medium, agent milestone blocker.

### A06 — High: the learned-content promotion boundary is ambiguous

**Location:** lines 125, 217–225 and `onto.context()` at 159. It is unspecified whether
`learned/*.md` participates in context before human review. If it does, a fabricated
convention becomes executable guidance before promotion, poisoning later evidence.
No proposal provenance, conflict resolution, expiration or rollback contract is given.

**Necessary change:** keep proposals in a separate, never-loaded location. Only the
operator-promoted manifest/notes enter the runtime snapshot. Proposals identify evidence,
applicable source, scope, uncertainty and superseded definitions; owner review records
accept/reject/edit and regression checks. Measure usefulness as well as junk rate.

**Acceptance:** adding a proposal or golden answer does not alter runtime context or
revision; promotion is explicit and cannot be performed by a data tool. Scope: small
for isolation, medium for a useful proposal workflow.

### A07 — High: partial data can be presented as a complete answer or export

**Location:** lines 201–205, 307–312, 345–346; MCP `result_rows`.
`ans.df` is the last result, not necessarily the result supporting the answer. The
MCP response defaults to 500 rows/256 KiB and marks truncation. Converting to a frame
and offering the rest as CSV cannot recover rows never fetched. Nonfinite values and
precise decimals arrive as strings, which also affects charts and comparisons.

**Necessary change:** carry result IDs, completeness status and type/units metadata
through answer/table/chart/export paths. Governed metrics should reject truncated
results when claiming completeness. Build a distinct bounded export/artifact path
before offering full CSV; never silently rerun a changing query to fill a download.

**Acceptance:** a result exceeding row or byte limits cannot appear as a complete
metric; chart/export share the same result; duplicate columns and exact decimals
survive conversion. Scope: small for rejection, medium for exports and typed envelopes.

### A08 — High: a second Warehouse and DuckDB ATTACH conflict with this server

**Location:** lines 26, 39, 97–99, 168–170, 256–258.
The server already owns Parquet and PostgreSQL access, validation, limits and writes.
A notebook Warehouse duplicates that boundary. The current DuckDB connection disables
external access except selected files and locks configuration; model-issued ATTACH is
intentionally incompatible. Combining directories currently unions one `data` table,
not unrelated Parquet datasets or Postgres tables in a federated join.

**Necessary change:** make Ana a client of data-mcp. Bind each metric explicitly to
one PostgreSQL source or selected Parquet root/paths and its dialect. Defer federated
joins to a separate controlled materialization/adapter design with snapshot, transfer,
credential and resource contracts. Do not switch on DuckDB external access globally.

**Acceptance:** both source types work through existing adapters; source credentials
never enter the model's tool arguments; unsupported federation fails explicitly.
Scope: small for basic integration; large for reliable federation.

### A09 — Medium: the database-role recipe is incomplete and its check is too weak

**Location:** lines 83–107. `ALTER DEFAULT PRIVILEGES` without `FOR ROLE` applies to
objects created by the executing role, not every ingestion owner. A rejected DELETE
at a regex/parser guard does not demonstrate that PostgreSQL itself denies writes.
Public function execution, role membership, SECURITY DEFINER routines and temporary
object permissions require deliberate scope when claiming a read-only capability.

**Necessary change:** run future-object grants for each actual owner, verify existing
privileges, and test the intended login directly against fixtures including a future
table and write-capable function. Use the database read-only transaction as a backstop.
[PostgreSQL default privileges](https://www.postgresql.org/docs/current/sql-alterdefaultprivileges.html)
and [privilege reference](https://www.postgresql.org/docs/current/ddl-priv.html) support
these distinctions. Scope: small; no production GRANT changes were made in this review.

### A10 — Medium: the metric schema does not specify enough meaning

**Location:** lines 132–149, 152–154, 433–435. Grain and prose omit executable contracts
for join cardinality/fan-out, key/null treatment, currency/units, exact numeric types,
date bounds/timezone, adjustment versions, source/dialect and output shape. An ambiguous
metric should request clarification, not automatically become ad-hoc guessed SQL.

**Necessary change:** start with explicit source, dialect, grain, description, units,
owner, reviewed date, timezone, SQL and expected output columns. Add typed parameters,
schema drift checks and fixture fan-out/null/time-boundary cases as the metrics require.
SQL visibility is evidence for review, not the whole trust model. Scope: medium.

### A11 — Medium: public-web requirements are substantially understated

**Location:** lines 274–277, 303–331, 367–375. Existing auth is assumed without inspecting
its deployment. Missing controls include request/body limits, CSRF or verified origins
for cookie-authenticated paid POSTs, rate limits across workers, secure session expiry,
shared concurrency admission, proxy/client deadlines and data-return policy.
A process-local semaphore is not a cross-worker cap.

**Necessary change:** keep UI gated; inspect the actual site's auth/deployment and
complete a minimal threat/abuse model before adding `/ask`. Render ontology text,
SQL and charts safely as well as prose. Pin/self-host a chart library if it enters
the data-facing page. Acceptance: unauthenticated/forged-origin/excess requests are
rejected before provider/database work. Scope: medium; no website deployment included.

### A12 — Medium: run retention creates a separate sensitive-data store

**Location:** lines 203–205, 311–324, 337–339. Questions, SQL literals, results and error
strings may contain restricted data or credentials. Timestamp filenames can collide;
session history contradicts the unqualified assertion of no state at line 362.
The `ana_runs` write also cannot use the read-only warehouse login.

**Necessary change:** UUID run IDs, private artifacts, bounded/redacted operational
logs, an explicit owner and retention/deletion policy, and a separate controller-owned
app-state credential. Do not give the model arbitrary access to run-history writes.
Distinguish one-shot conversation behavior from persistent user history. Scope: medium.

### A13 — Medium: token savings and monthly estimates are not reproducible

**Location:** lines 249–252, 325–328, 380–387. The TextQL percentages have no source or
benchmark protocol. Targeted searches and the inspected TextQL product/ontology pages
did not substantiate the exact 30%/41% claims; this is unverified, not proof of falsity.
[TextQL's ontology description](https://docs.textql.com/core/how-it-works/tools/ontology)
supports the architecture idea, not a transferable savings guarantee.

The $2/M input and $10/M output rates are **not a finding of stale pricing**: Anthropic's
[Sonnet 5 announcement](https://www.anthropic.com/research/claude-sonnet-5) includes an
August 10 update making those rates permanent. Account access and model selection still
need verification at use time. The monthly totals omit turns/token distributions,
failed attempts and cache writes, so they remain scenarios rather than forecasts.

**Necessary change:** date/source the pricing inputs and calculate cost from uncached
input, cache creation/read, output and failed-call usage. Record cache hit measurements;
[Anthropic caching documentation](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
specifies minimum lengths, expiry and write premiums. Five dispersed questions/day
need not share a live cache. Scope: small; no paid call was made.

### A14 — Medium: the plan presumes code exists and budgets by line count

**Location:** lines 14–15, 39, 97, 166–168, 303 and 399–415. The supplied file contains
no Warehouse/Ontology/Ana implementation, even though it says to drop those classes
in. It gives no versioned source for them. Rough hours/~400 lines exclude reproducible
packaging, database failures, policy, transport and tests. Ad-hoc pip/pandas/SQLAlchemy
also duplicate the existing template/uv/DuckDB/Psycopg stack.

**Necessary change:** use the production template project and locked dependencies;
replace guessed time/line targets with observable stage gates and a declared experiment
budget. Note that Mos Eisley's live MCP client is still absent rather than presenting
the hook as working. Scope: small planning correction; client work is a separate milestone.

### A15 — Low: deterministic metrics can be useful before the agent experiment

**Location:** lines 279–299, 291 and stage-7 gating. Metric execution can validate the
semantic layer without a model or web UI. It has zero model-token cost but still
incurs SQL latency, compute and maintenance, so zero latency/no cost is inaccurate.

**Potential change:** move named metric execution into the first MCP slice. Add UI
only if this is useful. Keep hand-maintained definitions even if the agent does not
beat the baseline. Scope: small; adopted in the integration design.

## Integration disposition

See [the revised plan](../ANA_LITE_PLAN.md) and
[verification record](ana-lite-verification.md) for actual implemented scope and tests.
The review does not authorize automatic learning promotion, paid model calls, a
production database migration or public deployment. Existing authorized data writes
remain a supported workflow; the analysis profile narrows them for analytical use.

Development integration verification: 55 tests (including disposable PostgreSQL),
Ruff, strict Pyright and package builds passed. See the linked verification record.
A02/A04/A07/A08 have concrete infrastructure mitigations; broader agent, data-lineage,
evaluation and public-deployment findings remain open as specified in the revised plan.
