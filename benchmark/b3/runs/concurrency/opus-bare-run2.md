1. Read-then-write on `counts` is not atomic, so two threads can both pass the check and exceed the limit — hold a lock (or use a single atomic operation) around the read/increment.
2. There is no time window at all, so counts only ever grow and every user is permanently banned after 100 requests — track a window (fixed or sliding) and reset or expire counts per window.
3. `counts` is per-process, so N workers each allow the full limit and the real ceiling is N × limit — move state to shared storage such as Redis, or accept and document the per-worker limit.
4. Nothing ever removes entries, so the dictionary grows without bound and leaks memory on unbounded user IDs — expire idle keys via TTL or a bounded cache.
5. The count increments only when the request is allowed, so rejected requests are invisible for backoff or abuse detection — count attempts separately from allowances if you need that signal.
6. `limit` is a per-call default, so a caller that omits or mistypes it silently gets 100 rather than the configured policy — take the limit from a config object owned by the limiter.
7. Unhashable or `None` user IDs raise or collapse into one shared bucket — validate the key before use.
8. The caller learns nothing but True/False, so it cannot send `Retry-After` or `X-RateLimit-Remaining` — return the remaining count and reset time alongside the decision.
9. Global mutable module state makes this untestable in isolation and unresettable between tests — wrap it in a class instance the caller owns.
10. A burst of the full limit in the first millisecond is treated identically to a smooth spread — use a token bucket if you want to smooth bursts.