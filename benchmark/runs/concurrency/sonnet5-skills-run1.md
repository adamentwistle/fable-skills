<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: s-conc-skills-1. Content below the line is the agent's final output, unmodified. -->

---

1. Check-then-act race: read `count`, compare to `limit`, then write are three separate steps — concurrent threads can both pass the check before either writes, admitting requests over the limit — fix: guard the read-compare-write with a per-user lock or atomic compare-and-swap.
2. Lost update on increment: two threads reading the same stale `count` both write `count+1`, so one increment is silently dropped — fix: same lock/CAS, or use an atomic counter (e.g. `itertools.count`, Redis `INCR`).
3. Bare dict mutation under concurrency is a data race with undefined interleaving (not just a logic bug) — fix: synchronize all access to `counts` through one lock (or move to a structure with atomic ops).
4. Per-process in-memory dict: each worker process has its own `counts`, so a "global" limit of 100 becomes `100 * num_workers` — fix: back the counter with shared external state (Redis/memcached) instead of a process-local dict.
5. No expiry/window at all: this is a lifetime cap, not a rate limit — once a user hits `limit` they're blocked forever — fix: add a time-bucketed (fixed/sliding) window and reset counts per window.
6. Unbounded memory growth: every distinct `user_id` gets a permanent dict entry that's never evicted — fix: add TTL-based eviction or an LRU-bounded store.
7. `user_id=None` (or any unvalidated value) is accepted as a valid, shared key, silently pooling all such callers under one limit — fix: validate/reject missing or malformed `user_id` before lookup.
8. Unhashable `user_id` types raise an uncaught `TypeError` at the dict lookup — fix: validate type or catch and handle at the boundary.
9. `limit` isn't validated: `limit&lt;=0` is silently accepted and just always denies (or, if negative, behaves inconsistently) — fix: validate `limit` is a positive int.
10. No documentation/enforcement that the function is not safe to call concurrently without external locking — fix: state and enforce the concurrency contract (internal lock or explicit caller requirement).
