1. Read-then-write is not atomic — two threads can both read 99 and both return True, letting the limit be exceeded; wrap the read/increment in a `threading.Lock` (or use an atomic backend op).
2. Under free-threaded builds (3.13+ `--disable-gil`) even the dict update itself races; same lock fixes it, don't rely on the GIL.
3. There is no time window, so this is a lifetime quota, not a rate limit — key on a time bucket or use a token bucket with refill.
4. Counters never decay, so a user is permanently blocked after 100 requests ever; add expiry/reset per window.
5. The dict grows without bound, one entry per distinct `user_id` — a memory leak and a cheap DoS by cycling fake IDs; add TTL eviction or a bounded LRU with a cap.
6. State is per-process, so with N workers the real limit is N×`limit` and is unpredictable behind a load balancer; move to a shared store (Redis `INCR`+`EXPIRE`) or accept `limit/N` explicitly.
7. `limit` is a per-call argument, so any caller can pass its own ceiling for the same user; take the limit from central config keyed by user tier.
8. No input validation — `None`/unhashable `user_id` raises `TypeError`, and `limit<=0` silently blocks everyone; validate and reject early.
9. `user_id` is used raw as the key, so untrusted input collides across tenants and bloats memory with long strings; namespace and length-cap the key.
10. The caller learns nothing but True/False — no remaining count or reset time to send as `Retry-After`; return the window reset alongside the decision.
11. Module-global mutable state can't be reset or injected in tests and is shared by unrelated callers; make it an instance of a limiter class.
12. Denied requests aren't recorded at all, so there's no signal for abuse detection or metrics; count attempts separately from allowances.