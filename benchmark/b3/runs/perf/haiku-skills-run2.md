1. Add index `CREATE INDEX events_org_created_idx ON events (org_id, created_at DESC)` to eliminate full table scan of 4.2M rows.
2. Replace sync `requests.get()` in `lookup_geo()` with async HTTP client (aiohttp); sync call blocks event loop, causing /healthz timeouts and pod restarts.
3. Batch user queries: fetch all actor_ids in one query before serialization, not one per event (N+1 problem).
4. Cap `_geo_cache` with `functools.lru_cache(maxsize=10000)` to stop memory growing from 310MB to 2.1GB in 20h.
5. Cap `_request_timings` list (rolling window or max size) to prevent unbounded growth.
6. Fix dedup: use `seen: set` not list (currently O(n²) on `in` checks).
7. **No**: don't ship on-call proposal — scaling workers and Redis cache don't fix sync blocking (pods restart), missing index, N+1 queries, or memory leak.