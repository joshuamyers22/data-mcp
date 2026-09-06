# Agentic Verification Loop: [objective]

Use for material work that needs multiple evidence-changing passes. Do not record
hidden reasoning, prompt/completion transcripts, unrestricted logs, secrets, client
data, or raw tool output.

## Objective and authority

- Requirement, issue, or project-brief link:
- User journey or operational outcome:
- Invariants and non-goals:
- Risk class: routine / material / high-risk or novel
- Implementation owner:
- Verifier or accountable approver, if required:
- Commit/revision and starting worktree state:

## Rubric

Define this before implementation. At least one dimension must directly measure the
project-specific objective.

| Dimension | Weight or blocking severity | Decision evidence | Pass threshold |
|---|---|---|---|
| Project-specific outcome | | | |
| Correctness and failure handling | | | |
| Security/privacy/data integrity | | | |
| Maintainability/operability | | | |

## Budget and stopping rules

- Maximum iterations:
- Elapsed-time or review window:
- Compute/cost ceiling, if material:
- Pass rule:
- Diminishing-return rule:
- Escalation/domain-input trigger:
- Rollback or abort condition:

The budget is a ceiling, not a target. Lines of code alone do not set it.

## Iterations

Each row must name new evidence or a meaningfully different perspective. Repeating the
same prompt against unchanged evidence is not another verification pass.

| # | Implemented slice | New evidence/context | Findings by severity | Decision and correction | Focused/full gates |
|---:|---|---|---|---|---|
| 1 | | | | | |

## Finding disposition

| ID | Location and evidence | Consequence | Severity | Accept/reject/defer rationale | Acceptance check | Owner |
|---|---|---|---|---|---|---|
| V-001 | | | | | | |

## Exit

- Stop reason: passed / diminishing returns / budget ceiling / blocked / escalated
- Rubric result and blocking findings:
- Full quality-gate command and result:
- Production-like replay/fault/rollback evidence, if applicable:
- Remaining uncertainty, owners, and dates:
- Human/domain approval, if required:
- Durable facts promoted to tests, ADRs, docs, or `PROJECT_MEMORY.md`:

## Diagnostic resource accounting (optional)

- Iterations and elapsed time:
- Aggregate tokens/cost, when policy permits:
- Accepted versus rejected findings:
- Escaped defects or regressions discovered later:

Resource use is interpreted alongside outcomes and guardrails; it is never proof of
quality by itself.
