# Release Readiness

- [ ] Critical journeys, invariants, and failure paths have evidence.
- [ ] Dependencies are locked, audited, and licensed appropriately.
- [ ] The semantic-version tag exactly matches project metadata.
- [ ] Build artifacts and SBOM are traceable to the commit.
- [ ] Secrets and private data are absent from source and artifacts.
- [ ] `PROJECT_MEMORY.md` is evidence-linked, deduplicated, current, and contains
      no secrets, private data, hidden reasoning, or restricted material.
- [ ] Tracked work notes are closed or current and contain no raw telemetry.
- [ ] Threats, migrations, compatibility, rollback, and recovery were reviewed.
- [ ] Logs, metrics, alerts, capacity, and operational ownership are adequate.
- [ ] Applicable latency budgets have production-like percentile, overload,
      replay, and regression evidence.
- [ ] Remaining risks have owners and dates.
- [ ] Material agent-assisted work has a requirement-linked rubric, evidence-changing
      verification passes, declared stop rules, and accountable risk approval.
- [ ] Applicable telemetry/error events conform to the versioned schema and feed
      a reproducible, owned improvement review with guardrails.
- [ ] Any telemetry storage/shipping/query component has target-host fault, capacity,
      health-export, privacy, recovery, and rollback evidence; scaffolding alone is
      not production approval.
