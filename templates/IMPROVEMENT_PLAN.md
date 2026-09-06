# Improvement Plan

## Target outcome

- User journey or system objective:
- Current evidence and reproducible query:
- Baseline window, count, rate, and uncertainty:
- Desired measurable state and assessment window:
- Constraints and behaviors that must not change:
- Guardrail metrics and rollback/stop condition:

## Verification-loop contract, when applicable

- Project-specific rubric and blocking threshold:
- New evidence or perspective required on each pass:
- Maximum iterations, elapsed time, and compute/cost ceiling:
- Diminishing-return and domain-escalation rules:
- Verification-loop record: `templates/AGENTIC_VERIFICATION_LOOP.md` copy or N/A

| Priority | Finding/risk | Signal or error code | Smallest safe slice | Acceptance evidence | Owner | Due | Status |
|---:|---|---|---|---|---|---|---|
| 1 | | | | | | | Not started |

## Execution notes

For each slice: add or identify the safety net, make the change, run focused and
full gates, document before/after evidence on a later assessment window, remove
obsolete paths, and retain a clear rollback point. A reduction in logs or errors
does not count if user outcomes or guardrails regress. Repeating review against
unchanged evidence is not another verification pass; resource budgets are ceilings,
not proof of quality.

## Deferred items

Record why each item is deferred, its trigger for reconsideration, and owner.
