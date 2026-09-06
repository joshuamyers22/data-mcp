# Telemetry Review: [service or workflow]

- Owner:
- Review period (UTC):
- Environment and release/revision range:
- User journey or system objective:
- Related SLI/SLO, incident, issue, or prior review:

## Evidence contract

- Event schema version:
- Queries/dashboard/export digest needed to reproduce aggregates:
- Known sampling, dropped-event, clock, cardinality, or retention limits:
- Privacy/access review and redactions:
- Comparison window or baseline:

Never attach unrestricted raw logs to this review. Preserve a controlled query or
content-addressed aggregate when policy permits.

## Observations

Separate observed telemetry from inferred cause.

| Signal/event/error code | Count and rate | Affected journeys | Release/segment | Evidence | Confidence |
|---|---:|---|---|---|---|
| | | | | | |

## Selected improvement

- Problem selected and why it outranks alternatives:
- Hypothesized cause; disconfirming evidence:
- Smallest safe change:
- Correctness, security, privacy, and reliability invariants:
- Owner and due date:
- Rollback or stop condition:

## Verification plan

- Regression test or replay:
- Before/after measures and minimum useful effect:
- Guardrail metrics:
- Assessment window not used to select the change:
- Result: improved / unchanged / regressed / inconclusive
- Decision and follow-up:

If this review evaluates an agentic verification workflow, aggregate stable loop
events by rubric and stop reason. Interpret iterations, token/cost totals, and finding
counts only alongside accepted findings, escaped defects, regressions, user outcomes,
and guardrails. Never attach prompts, completions, hidden reasoning, unrestricted diffs,
or raw reviewer prose.

Link the accepted action from `templates/IMPROVEMENT_PLAN.md`. Update project
memory only when the review establishes a durable fact worth retrieving later.
