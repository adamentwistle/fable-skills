1. Missing composite index on (org_id, created_at) — causes 1.2-1.6s query for large orgs; create with CREATE INDEX CONCURRENTLY
2. N+1 user SELECT queries in serialize_event — each event fetches user separately; batch fetch all users in one query before serialization
3. Blocking requests.get() in serialize_event — lookup_geo blocks event loop causing /healthz timeout and pod restarts; convert lookup_geo to async with httpx
4. Unbounded _geo_cache dict — no eviction or TTL; implement with functools.lru_cache
5. Unbounded _request_timings list — never trimmed, grows forever; cap with collections.deque(maxlen=10000)
6. O(N) deduplication — seen: list has O(N) membership test; use set for O(1)
7. Do not ship the proposal. Add the index first (CREATE INDEX CONCURRENTLY, takes ~5 min), then fix N+1 queries and memory leaks in parallel; query will drop to <50ms and serialization to <200ms, making caching and worker scaling unnecessary.