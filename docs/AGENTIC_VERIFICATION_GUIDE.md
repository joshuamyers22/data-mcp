# Bounded Verification Loops for Agent-Assisted Engineering

## Purpose

Agent-assisted work benefits from iteration only when each pass adds evidence or a
meaningfully different review perspective. Repeating unconstrained self-review can
compound an early mistake, rationalize a compromise after context loss, drift from the
product goal, and consume substantial compute without improving the result.

Use this guide for material implementation, investigation, migration, security,
correctness, data-integrity, or production-readiness work. Routine edits normally need
the repository's standard quality gate, not a ceremonial multi-pass process.

## Source assessment

This guidance synthesizes two Markdown essays supplied locally on 2026-09-05:

| Artifact | SHA-256 | Supported contribution |
|---|---|---|
| `agentic-loops-verification.md` | `9fe4bcb61e28b02a91492c72fe6c27f185d9b1bf6147caa8c7bdaf6ad329e488` | Early verification, explicit rubrics, context-diverse review, a project/spec north star, and stopping thresholds. |
| `token-spending-agents.md` | `ba0154db60f5de99f17472e64d8dad4dac42b59f57f50f28f9a0b8f8687780c2` | Extra attempts can explore alternatives, recover from weak paths, and fund tool-backed verification; novelty still needs domain guidance. |

The files are informal opinion essays with anecdotal experience, no reproducible data,
no controlled comparison, and no complete citation trail for their quantitative
claims. They do **not** establish that defects decrease monotonically with token use,
that enough compute solves every non-novel problem, that fresh agent contexts are
independent, or that token budget should be proportional to lines of code. Those claims
are hypotheses to evaluate, not template policy. The locally supplied essays are not
copied into this repository; their hashes identify the reviewed inputs.

## The production loop

1. **State the north star.** Link the requirement, user journey, invariants, threat or
   failure model, and explicit non-goals. A verifier cannot detect drift from an
   unstated objective.
2. **Design the rubric before implementation.** Include at least one project-specific
   outcome dimension. Assign blocking severities and name the command, replay,
   inspection, or external evidence that can decide each dimension.
3. **Set a bounded budget and exit rules.** Bound iterations, elapsed time, and—when it
   matters—compute or cost. A budget is a ceiling, not a target to spend. Define pass,
   diminishing-return, escalation, and blocked conditions before the loop begins.
4. **Implement the smallest coherent slice.** Preserve a rollback point and run the
   cheapest relevant check immediately. Early evidence prevents an invalid assumption
   from becoming infrastructure.
5. **Change the evidence or perspective.** A later pass must add something material:
   a focused test, static analysis, fault injection, production-like replay, clean
   build, adversarial input, requirement trace, human/domain review, or an independently
   briefed reviewer when the workflow authorizes one. Repeating the same prompt against
   the same evidence is not a new verification pass.
6. **Triage findings, then correct.** Every finding needs a location, evidence,
   consequence, severity, smallest safe correction, and acceptance check. Do not apply
   verifier suggestions merely because they were generated; reject unsupported or
   scope-expanding advice with a recorded reason.
7. **Re-run focused and full gates.** A fix is not complete until its reproducer passes,
   relevant regressions are covered, and the repository gate remains green.
8. **Stop deliberately.** End on the declared pass threshold, on the iteration/budget
   ceiling, after the declared number of passes with no new material evidence, or when
   domain authority is required. Report unresolved findings rather than looping until
   they disappear from the narrative.

For safety, security, governance, financial logic, or release approval, an agent's own
review is never the sole approval. Fresh context can reduce anchoring but does not prove
independence or correctness. Executable evidence and accountable human/domain review
remain authoritative.

## Budget by risk and uncertainty

Scale verification effort using risk, novelty, uncertainty, blast radius, reversibility,
dependency reach, and the strength of existing tests. Lines of code can help estimate
inspection effort, but generated code, configuration, a one-line authorization defect,
or a schema change makes it a poor standalone proxy.

Use three practical bands:

- **Routine/reversible:** one implementation pass, focused checks, and the normal gate.
- **Material/cross-cutting:** written rubric, incremental verification, an additional
  evidence source or perspective, and explicit stop conditions.
- **High-risk/novel:** domain owner, threat/failure model, independent approval,
  production-like replay or fault evidence, rollback exercise, and a separately
  approved resource budget.

When the core uncertainty is genuinely novel or domain-specific, stop spending compute
on unconstrained implementation. Obtain data, a domain decision, a prototype result, or
a human-authored invariant first. More attempts cannot substitute for missing ground
truth.

## Recording and telemetry

Use `templates/AGENTIC_VERIFICATION_LOOP.md` when a loop spans multiple meaningful
passes or needs auditability. Keep disposable output in ignored `.work/`; never record
hidden reasoning or a prompt transcript.

If operational telemetry for the workflow is justified, use the shared schema with
stable events such as `verification_started`, `finding_recorded`,
`verification_completed`, and `verification_stopped`. Allowlisted attributes may
include `iteration`, `rubric_id`, `finding_severity`, `finding_count`, `gate_name`, and
`stop_reason`. Token and cost totals may be retained as controlled aggregates for
capacity planning, but they are diagnostic inputs—not quality objectives.

Never emit prompts, completions, chain-of-thought, unrestricted diffs, tool arguments or
results, credentials, source code, client data, or raw reviewer prose. Measure accepted
findings, escaped defects, regressions, user outcomes, elapsed time, and cost together;
optimizing token count, finding count, or loop count alone invites gaming.

## Exit evidence

A completed loop identifies:

- the requirement and rubric version used;
- the evidence added by each pass;
- blocking findings resolved, rejected, deferred, or still open;
- focused and full gate results;
- actual stop reason and remaining uncertainty;
- accountable approval when the risk class requires it.

Use the resulting durable facts to update tests, an ADR, maintained documentation, or
project memory. The loop record is coordination evidence, not a new source of product
authority.
