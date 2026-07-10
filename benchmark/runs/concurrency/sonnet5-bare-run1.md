<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: s-conc-bare-1. Content below the line is the agent's final output, unmodified. -->

---

1. Check-then-act race: `get` then `set` isn't atomic, concurrent threads can both pass the check and both increment past `limit` — use a per-user lock or an atomic increment (e.g. `Lock`/`threading.Lock`, or `collections.Counter` with `itertools` atomic ops, or a DB/Redis `INCR`).
2. Multi-worker processes each have their own `counts` dict, so the real limit becomes `limit × num_workers` — move state to a shared store (Redis/Memcached) instead of an in-process dict.
3. No time window: once a user hits `limit` they're blocked forever, this isn't "rate" limiting at all — track counts per fixed/sliding window (e.g. bucket by `time.time()//window`) and reset/expire accordingly.
4. Unbounded memory growth: every distinct `user_id` gets a permanent dict entry that's never evicted — add TTL/expiry or use a bounded LRU/cache structure.
5. No input validation on `user_id` — reject `None`/non-hashable/malformed keys to prevent unbounded key injection (DoS via cardinality explosion).
6. No validation of `limit` (zero/negative silently blocks everything with no error) — validate and raise/log on invalid config.
7. State is lost on process restart/deploy, allowing a burst right after restart — persist counters externally (Redis) if burst-avoidance matters.
8. No mechanism to reset counts (e.g. new time window) even conceptually — needs an explicit expiry/reset path, not just monotonic increment.
9. Reliance on CPython GIL for "safety" is fragile and non-portable (breaks under free-threaded builds/PyPy/JIT) — use explicit locking rather than assuming GIL atomicity.
10. Not distributed across hosts, so a service replicated across machines gets `limit × num_hosts` effective throughput — centralize state in shared storage for a true global limit.
