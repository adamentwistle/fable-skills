1. Missing index on (org_id, created_at) forces full table scan of 4.2M rows, explaining 1.2–1.6 s query time.
2. Add `CREATE INDEX events_org_created_idx ON events (org_id, created_at DESC)`.
3. N+1 query problem: serialize_event does one fetchrow per event, so 1000 individual actor queries per request.
4. Batch fetch actors with `JOIN users` or `WHERE actor_id IN (...)` subquery instead.
5. Unbounded _geo_cache and _request_timings grow indefinitely, explaining memory leak from 310 MB to 2.1 GB in 20 h.
6. Bound _geo_cache to ~10k entries with LRU eviction; bound _request_timings similarly.
7. serialize_event list comprehension awaits sequentially instead of concurrently, blocking serialization.
8. Use `asyncio.gather(*[serialize_event(...) for ...])` to parallelize.
9. requests.get() in lookup_geo is synchronous, blocking the worker on cache misses (2 s timeout), causing /healthz to hang.
10. Mitigate by ensuring high cache hit ratio with the bounded _geo_cache above; can replace with async httpx later.
11. Add LIMIT to initial SELECT: currently fetches unlimited rows then filters in Python.
12. **Do NOT ship the on-call proposal**: scaling workers and pools won't fix the root cause (missing index, N+1 queries); Redis cache is premature band-aid; fix index and N+1 first, likely sufficient without new infrastructure.