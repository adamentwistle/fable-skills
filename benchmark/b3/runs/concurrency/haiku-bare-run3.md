1. Race condition: check and increment are separate operations, allowing count to exceed limit — wrap both in `threading.Lock()`.
2. No time window: counts never reset, so limit is permanent ban after N requests, not "N per period" — add timestamp tracking with sliding or fixed windows.
3. Memory leak: user entries accumulate forever — add TTL-based cleanup or delete keys after reset window passes.
4. Multi-worker bypass: each worker process has its own `counts` dict, so limit is multiplied by worker count — move to shared backend (Redis, Memcached).
5. Dict mutation not thread-safe: concurrent reads/writes can corrupt the dict structure itself — protect all dict access within the lock, not just the logic.