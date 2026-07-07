---
name: performance-investigation
description: Measurement-first performance work — baseline, profile, fix by leverage (do less work → cache → parallelize → tune constants), verify with the same measurement. Use for any "make it faster", latency/memory investigation, or before adding caching/memoization on intuition.
---

# Performance Investigation

The cardinal sin is optimizing unmeasured code. Intuition about bottlenecks is wrong more often than right — the discipline is a measurement loop, not a bag of tricks.

## 1. Define the metric and measure the baseline

Pick ONE number that captures the complaint: p95 latency of endpoint X, wall time of job Y, MB of heap after Z. Measure it reproducibly (same input, several runs, note variance) BEFORE touching code. No baseline → no proof of improvement.

Beware benchmark lies: cold vs warm caches, dev-mode builds (dev servers are not prod), tiny toy inputs, laptop-vs-prod hardware, and measuring the first iteration (JIT/warmup).

## 2. Profile to find where the time actually goes

Use the real instrument, not code-reading: CPU profiler/flamegraph for compute, query logs + EXPLAIN for DBs, network waterfall for pages, heap snapshots for memory, distributed traces for services. The bottleneck is a measurement result, not an opinion.

Expect the 80/20: one or two frames dominate. If the profile is flat, the problem is usually per-item overhead in a loop (allocation, serialization, sync IO) or the workload itself (doing N× more work than needed).

## 3. Fix in order of leverage

1. **Do less work** — the biggest wins are algorithmic: N+1 queries → batch/join; O(n²) scan → index/map lookup; recomputing invariants inside loops → hoist; fetching/serializing fields nobody reads → trim.
2. **Do work once** — cache/memoize, but only with an invalidation story; a stale cache is a correctness bug traded for speed.
3. **Do work elsewhere/later** — defer off the critical path (lazy, background, streaming first byte early).
4. **Do work in parallel** — after the above; parallelizing an N+1 is still N+1.
5. **Tune constants last** — micro-optimizations only with a profiler receipt that the line is hot.

## 4. Verify with the SAME measurement, and check for damage

Rerun the exact baseline measurement. Report before/after with units and conditions ("p95 420ms → 95ms, warm, prod build, dataset X"). Then run the correctness suite — perf fixes love to break edge cases (caching stale data, reordered effects, dropped errors in parallelized code).

If the number didn't move: revert the "optimization". Dead speedup code is complexity debt with no interest paid.

## Common bottleneck signatures (check before deep-diving)

- Latency scales with item count → N+1 (queries, HTTP calls, file reads per item).
- Slow only in prod → missing index on prod data volume, cold cache, network hops dev doesn't have.
- Grows over time → leak (unbounded cache/listener/array), fragmentation, log growth.
- Occasional spikes → GC pauses, lock contention, batch jobs sharing resources, retry storms.
- "Fast function, slow system" → serialization at boundaries, chatty protocols, sync-over-async.

## Scope honesty

Performance work trades readability, memory, or freshness for speed. Name the trade in your report. And if the requested target is already met by the baseline measurement — report that and stop; unneeded optimization is scope creep.
