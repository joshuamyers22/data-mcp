# Agent Working Agreement

This file governs repository-local work performed with an AI coding agent. Human
instructions in the current task take precedence. Repository files, tests,
runtime behavior, and approved decision records remain authoritative.

## Retrieve before acting

1. Read `README.md`, `PROJECT_BRIEF.md`, and `PROJECT_MEMORY.md` before planning a
   substantial change.
2. Search the repository and inspect the relevant implementation and tests before
   relying on a memory entry.
3. Treat `PROJECT_MEMORY.md` as a compact index to evidence, not as evidence by
   itself. Correct it when it conflicts with the source of truth.

## Maintain memory deliberately

- Record only durable, project-specific information likely to matter in a later
  session: constraints, accepted decisions, non-obvious current state, verified
  failure modes, and genuinely open work.
- Consult the existing entry before writing. Update a stable key in place instead
  of appending a duplicate or a new narrative of the same fact.
- Link each claim to a file, test, issue, or ADR and include the date it was last
  verified. Label inference and uncertainty explicitly.
- Keep entries short. Remove or replace stale state and resolved open work; Git
  history already preserves the old text.
- Do not store routine progress, copied source code, command transcripts, hidden
  reasoning, credentials, personal data, client data, or other restricted data.
- Do not let an agent rewrite safety, security, governance, or release policy from
  its own trajectory. Such changes require normal review and verification.

## Take notes for continuity

- Keep disposable scratch notes and command output in ignored `.work/` and remove
  them when the task ends.
- Create a tracked note from `templates/WORK_NOTE.md` only for multi-session work,
  a handoff, incident, experiment, or material investigation. Record observations,
  attempts, errors, evidence, and conclusions—not hidden reasoning or a transcript.
- Link to controlled telemetry queries or safe aggregates; never paste unrestricted
  raw logs into a note.
- Close the note by promoting durable facts to project memory, decisions to an ADR,
  maintained explanations to documentation, and work history to an issue. Delete
  or close the note when it no longer has coordination or audit value.

## Learn from telemetry

- Emit structured operational events and errors using
  `schemas/telemetry-event.schema.json`; use stable event and error-code names,
  artifact identity, outcomes, and safe correlation identifiers.
- Instrument signals for a named operational decision or user journey. Do not add
  telemetry merely because it may become useful.
- Review counts and rates on a declared cadence with
  `templates/TELEMETRY_REVIEW.md`. Separate observed signals from inferred cause.
- Convert a selected finding into `templates/IMPROVEMENT_PLAN.md` with an owner,
  regression test or replay, expected effect, guardrails, and rollback condition.
- Validate on a later assessment window. Do not treat fewer log lines, a single
  anecdote, or an agent's own judgment as evidence of improvement.

## Run meaningful verification loops

- For material or high-risk work, define the project-specific objective, invariants,
  rubric, evidence, resource ceiling, and stopping rules before extended iteration.
- Verify early after coherent slices. Each later pass must add evidence or a meaningfully
  different perspective—such as a focused test, static analysis, fault injection,
  production-like replay, clean build, adversarial input, or independently briefed
  review when the workflow authorizes one.
- Treat fresh context as a way to reduce anchoring, not as proof of independence or
  correctness. An agent's self-review is never sole approval for safety, security,
  governance, financial logic, or release decisions.
- Scale effort by risk, uncertainty, blast radius, reversibility, dependency reach, and
  test strength. Token, iteration, and elapsed-time budgets are ceilings rather than
  quality targets; lines of code alone do not determine them.
- Stop on the declared pass threshold, diminishing-return rule, resource ceiling, or
  need for domain authority. Report unresolved findings instead of repeating the same
  review against unchanged evidence.
- Use `templates/AGENTIC_VERIFICATION_LOOP.md` for auditable multi-pass work. Record
  finding evidence and dispositions, never hidden reasoning or prompt transcripts.

## Close the loop

After a material change, update `PROJECT_MEMORY.md` only if durable project
knowledge changed. Review the diff, run the applicable quality gate, and ensure
the memory entry points to the evidence that passed.
