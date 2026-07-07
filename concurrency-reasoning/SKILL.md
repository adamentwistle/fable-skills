---
name: concurrency-reasoning
description: Async/concurrent/streaming discipline — five questions (overlapping runs, check-then-act, mutation across await, response ordering, cancellation), idempotent retries, shared-state audit, race amplification. Use for async fan-out, streams/SSE, jobs, caches, or flaky timing-smell bugs.
---

# Concurrency Reasoning

Concurrency bugs don't announce themselves in review — the code reads fine sequentially. The discipline is asking a fixed set of questions about every async surface, because the compiler won't.

## The core question set (ask for every async/shared surface)

1. **What happens if this runs twice, overlapping?** Two clicks, two requests, a retry racing the original, cron overlapping its previous run. If the answer involves corrupted state or double effects, you need a guard (idempotency key, mutex, request de-dupe, disable-on-click).
2. **What happens between the check and the act?** Every `if (exists) then update` on shared state is a TOCTOU window. Close it with atomic operations (upsert, compare-and-swap, unique constraints, transactions) — not with a smaller window.
3. **Who else mutates this while I await?** Every `await` is a yield point: module-level variables, caches, and objects captured by closures can change under you mid-function. Re-read state after awaits if it matters; don't cache pre-await reads across the gap.
4. **What order do these land in?** Two in-flight requests resolve in either order. If responses update the same state (search-as-you-type, autosave), guard with sequence numbers / "latest wins" checks / cancellation of the superseded one.
5. **What happens on cancellation/unmount/disconnect mid-flight?** Streaming handlers and UI callbacks firing after teardown → guard with abort signals, mounted flags, or subscription cleanup. Partial effects from an aborted multi-step operation need cleanup or resumability.

## Retries and exactly-once

- **Retry only idempotent operations** — or make them idempotent first (idempotency keys, natural unique constraints). A retried "create" without one is a duplicate.
- Retries need backoff + jitter + a cap; retrying immediately in a loop is a DoS on your own dependency.
- Distinguish "the request failed" from "the request's *response* failed" — the operation may have succeeded server-side. Design reads-back or upserts accordingly.

## Shared-state audit (for the diff you're writing)

Enumerate every piece of state your async code touches that outlives one invocation: module globals, singletons, caches, class fields, DB rows, files. For each: who writes it, from how many concurrent contexts, and what serializes those writes? "Nothing serializes them, but it's probably fine" is a bug report from the future.

## Debugging suspected races

- Flaky test / intermittent failure → don't rerun until green. Amplify instead: run 20–100× in a loop, add load, add artificial delays (`sleep` at suspected interleaving points) to widen the window and make it deterministic.
- Bisect by interleaving, not by code: log timestamps + IDs at each async boundary and reconstruct the actual order of the failing run.
- The fix must name the interleaving it prevents. "Added a lock and it stopped failing" without knowing the race is a hidden deadlock waiting.

## Deadlock/starvation reflexes

Consistent lock ordering; never hold a lock across an await/IO; timeouts on anything that waits on another party; bounded queues (an unbounded queue turns backpressure into an OOM).
