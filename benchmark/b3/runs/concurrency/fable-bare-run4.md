1. Check-then-increment is not atomic across threads, so concurrent requests past the limit are both allowed and increments are lost; guard the read-modify-write with a lock or use an atomic increment.
2. `counts` is per-process, so N workers each enforce their own limit and the real limit is N×100; move state to a shared store with atomic INCR (e.g. Redis).
3. No time window: counts never reset, so a user is blocked forever after 100 requests; add a window with expiry (fixed/sliding window or token bucket).
4. Unbounded memory: every user_id ever seen stays in the dict; evict entries on window expiry or use an LRU/TTL structure.
5. State vanishes on restart or deploy, resetting all limits; keep it in the external store from finding 2.
6. `limit` is a per-call argument, so different callers can enforce different limits on the same key; configure the limit per key/tier once, not per call site.
7. No key normalisation: `1` and `"1"` are separate buckets, `None` becomes a shared bucket, and unhashable ids raise `TypeError`; validate and normalise user_id.
8. Even if a window is added, a fixed window permits a 2× burst at boundaries; use a sliding window or token bucket.
9. Return value carries no remaining/retry-after info for headers or backoff; return a result object with remaining and reset time.
10. Rejected requests are not counted or logged, so abuse is invisible; emit metrics on both paths.
11. Global mutable state makes it untestable and non-injectable; wrap in a class with an injected store and clock.
12. No monotonic clock is used anywhere, so any window you add will break on wall-clock changes; use `time.monotonic()` or store-side TTLs.
13. Failure policy is undefined once state is external (fail-open vs fail-closed on store timeout); decide and enforce explicitly.
14. Relies on CPython GIL luck for the two dict ops; free-threaded Python (3.13+ no-GIL) removes even that, so the lock in finding 1 is mandatory.