1. Check-then-set race: two threads can both read the same count and both pass, admitting more than `limit`; guard with a lock or use an atomic INCR.
2. Lost updates from the same race under-count real traffic, so the limiter is both leaky and inaccurate; same fix.
3. No time window: counts never reset, so every user is permanently blocked after 100 requests; add a fixed/sliding window or token bucket keyed on time.
4. Per-process state: each worker has its own `counts`, so the effective limit is `limit × workers` and depends on which worker the balancer picks; move state to a shared store like Redis with INCR+EXPIRE.
5. State is lost on restart or deploy, letting every user burst afresh; same shared-store fix.
6. Unbounded memory: `counts` grows by one entry per distinct `user_id` forever; evict entries with a TTL or LRU.
7. No key validation: `None` or empty ids collapse all anonymous callers into one bucket, and unhashable ids raise; reject or normalize ids before counting.
8. `limit` is a per-call argument, so different call sites can enforce different limits on the same shared counter; bind the limit to a policy config, not the call.
9. `limit <= 0` silently denies everything with no error; validate config at startup.
10. Any concurrent iteration over `counts` (metrics, admin endpoints) can raise "dictionary changed size during iteration"; snapshot under the lock.
11. Caller gets only a bool, no remaining count or reset time, so it cannot emit `Retry-After`; return a result object with remaining and reset.
12. Not safe for free-threaded Python 3.13+ either, where even the dict write ordering is no longer serialized by the GIL; the lock in item 1 covers this.
13. Module-level global makes the limiter untestable and shared across unrelated endpoints; wrap it in a class instance injected per policy.