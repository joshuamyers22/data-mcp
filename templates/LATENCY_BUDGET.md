# Latency and Capacity Budget

Complete this record for any latency-sensitive path. Use one document per path or
workload class. Link raw results and the benchmark/replay command; prose alone is
not acceptance evidence.

## Scope

- Path and business outcome:
- Start event / end event:
- Correctness boundary if a deadline is missed:
- Owner and review date:
- Production hardware, OS, runtime/compiler, and topology:
- CPU model/stepping/features, firmware/microcode, kernel, and power policy:
- Core placement, SMT, NUMA, frequency, thermal, isolation, and virtualization:
- Workload/data-set version and traffic mix:
- Measurement clock and instrumentation overhead:

## End-to-end objective

| Load | p50 | p95 | p99 | p99.9 | Maximum/jitter | Throughput | Error/loss limit |
|---|---:|---:|---:|---:|---:|---:|---:|
| Expected | | | | | | | |
| Peak | | | | | | | |
| Overload | | | | | | | |

## Stage budget

| Stage | Owner | p99 budget | Allocation/blocking allowed? | Queue capacity / max age | Failure or degradation behavior |
|---|---|---:|---|---|---|
| | | | | | |

## Time and ordering

- Wall-clock source and synchronization:
- Monotonic duration clock:
- Source, receive, decision, and transmit timestamp definitions:
- Sequence/gap/duplicate/reordering policy:
- Clock-step, drift, and synchronization-loss behavior:
- Replay inputs and configuration identity:

## Resource bounds

- Maximum in-flight work:
- Memory/allocator/page-fault assumptions:
- Thread ownership, affinity, NUMA, and isolation assumptions:
- External dependency deadlines:
- Backpressure, rejection, shedding, and stale-data policy:
- Startup, warm-up, shutdown, and drain limits:

## Evidence

- Build revision/digest, compiler/linker versions, flags, and target architecture:
- Warm-up, sample count, repetitions, run order, and baseline variance:
- Profiler, compiler report, disassembly, and performance-counter artifacts:
- Counter availability, multiplexing, privilege, skid, and scaling limitations:
- Raw results and completed `PERFORMANCE_EXPERIMENT.md` record:

| Scenario | Command / artifact | Result distribution | Decision |
|---|---|---|---|
| Baseline | | | |
| Peak | | | |
| Overload | | | |
| Dependency failure | | | |
| Replay/determinism | | | |

## Change control

- Performance hypothesis:
- Correctness and risk controls that may not change:
- Before/after evidence:
- Complexity introduced:
- Rollback trigger and procedure:
- Approver and date:
