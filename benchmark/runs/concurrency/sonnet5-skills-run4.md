<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: s-conc-skills-4. Content below the line is the agent's final output, unmodified. -->

---

1. Check-then-act race: read→compare→write isn't atomic, so concurrent threads can both pass `count &lt; limit` before either writes — fix with a lock (or atomic compare-and-swap) around the whole read-modify-write.
2. Lost update on increment: two threads reading the same `count` both write `count+1`, silently dropping one increment and letting more than `limit` requests through — fix by making increment atomic (lock, `itertools.count`, or `INCR` in a shared store).
3. Shared mutable `counts` dict has no synchronization at all for compound ops — fix with a `threading.Lock` per key (or one global lock) guarding get+set.
4. Per-process global dict doesn't cross multiple worker processes — each worker gets its own counter, so the effective limit is `limit × num_workers`, not `limit` — fix by moving state to a shared external store (Redis/Memcached) or process-shared memory.
5. No isolation across machines either if deployed on multiple hosts — same per-process flaw compounds cluster-wide — fix: centralize counters in Redis or similar.
6. No time window: counts never reset, so this is a lifetime cap per user, not a rate limit — fix by tracking window start/expiry (fixed/sliding window or token bucket) and resetting/decaying counts.
7. Unbounded memory growth: every distinct `user_id` gets a permanent dict entry with no eviction — fix with TTL expiry or an LRU-bounded cache.
8. `user_id=None`/missing not validated — `None` becomes a real (shared) dict key, letting unauthenticated callers share one bucket — fix by rejecting falsy/invalid `user_id` up front.
9. Under concurrency the "exactly at limit" boundary is only correct if the race in #1/#2 is closed — restate: boundary logic is right sequentially but unenforced under load.
10. No validation of `limit` (e.g., zero/negative) — fix by validating `limit &gt; 0` and raising/erroring otherwise.
11. Process restart/crash resets all counts to zero, letting a user regain full quota via a redeploy or crash-loop — fix by persisting counts in the external store, not process memory.
