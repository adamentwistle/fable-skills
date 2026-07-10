<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: conc-skills-2. Content below the line is the agent's final output, unmodified. -->

---

1. Check-then-act race: `get` → compare → write isn't atomic, so two threads both read 99 and both pass, exceeding the limit — wrap the read-modify-write in a `threading.Lock`.
2. Lost update on increment: concurrent `counts[user_id] = count + 1` from the same base value drops one increment, undercounting and letting extra requests through — same lock (or an atomic counter) fixes it.
3. Shared mutable `counts` dict is mutated by multiple threads with no synchronization at all — guard every access with a lock.
4. Per-process state: each worker holds its own `counts`, so the effective global cap is `workers × limit`, not `limit` — move state to a shared store (Redis/Memcached) for a true global limit.
5. No time window — count only ever grows, making this a permanent lifetime cap, not a rate limit; once at limit the user is blocked forever — use expiring per-window buckets (sliding/fixed window).
6. Unbounded memory growth: every distinct `user_id` adds a key that is never evicted — add TTL/LRU eviction (naturally handled by windowed keys with expiry).
7. Missing/`None` `user_id`: `None` (or empty) becomes a shared bucket that lumps all anonymous callers together — validate and reject falsy `user_id` before counting.
8. Boundary semantics: `count &lt; limit` permits exactly `limit` requests (indices 0–99 for limit=100) then blocks — confirm "100 allowed" is the intended inclusive/exclusive meaning.
9. `limit` is a per-call argument with no consistency guarantee — different callers passing different limits for the same user yield incoherent enforcement; make the limit a property of the limiter, not the call.
