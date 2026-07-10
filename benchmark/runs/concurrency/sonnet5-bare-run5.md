<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: s-conc-bare-5. Content below the line is the agent's final output, unmodified. -->

---

Quicknode's terse findings on this rate limiter:

1. Check-then-act on `counts` isn't atomic — two threads can both read `count &lt; limit` before either writes, letting requests exceed `limit`; fix with a per-user lock or atomic `INCR`.
2. No time window at all — once a user hits `limit` they're blocked forever, not "per interval"; fix by tracking a window start/expiry (fixed or sliding window) and resetting counts when it elapses.
3. State is a local in-process dict — multiple workers/processes each have their own `counts`, so the real limit is `limit * num_workers`; fix by moving state to a shared store (Redis, etc.) with atomic increment.
4. `counts` grows unbounded forever (one key per user_id, never removed) — memory leak; fix with TTL/eviction or periodic cleanup of stale entries.
5. State is lost on process restart/crash/deploy — limiter resets silently; fix by persisting counts externally if that matters for the SLA.
6. `limit` is a caller-supplied parameter rather than fixed per user — inconsistent callers can pass different limits and get different enforcement for the same user; fix by binding limit to config/user, not the call site.
7. No validation of `user_id` (None, unhashable, empty) — can raise or silently create bogus keys; fix by validating/normalizing the key before use.
8. No mechanism to reset/clear a user's count (e.g., on ban lift or admin override) — fix by exposing a reset/delete op alongside `allow_request`.
9. Not distributed-safe — behind a load balancer with multiple hosts, each host has an independent counter; fix same as #3, a shared atomic backing store.
