1. Race condition: check and increment aren't atomic; use lock or atomic operation.
2. No time window: counts persist forever, blocking users permanently; use sliding window or TTL.
3. Memory leak: old entries never deleted; clean up stale user IDs or set expiry.
4. Thread-unsafe: unprotected dict access corrupts state; protect with `threading.Lock()`.
5. Multi-worker broken: separate processes have isolated dicts; use shared backend (Redis, etc.).