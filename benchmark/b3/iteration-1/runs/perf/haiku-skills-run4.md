1. Add index on `events(org_id, created_at DESC)` to speed up the SELECT from 1.4 s to <100 ms.
2. Use `DISTINCT ON (dedupe_key)` with `ORDER BY dedupe_key, created_at DESC` in SQL to deduplicate at the database level instead of in app code.
3. Batch user lookups — replace 1000 individual `fetchrow` queries in `serialize_event` with one `WHERE actor_id IN (...)` query.
4. Fix blocking sync I/O in `lookup_geo` — replace `requests.get()` with `httpx.AsyncClient` or move to a background thread; this unblocks the event loop and stops /healthz from hanging.
5. Bound `_geo_cache` with an LRU eviction or TTL to prevent unbounded growth.
6. Clear `_request_timings` list periodically in `/internal/metrics` response or use a bounded deque; it accumulates 8.6 M entries in 20 h, contributing to the 1.8 GB memory leak.
7. Measure on prod data to confirm p95 drops below acceptable latency.
8. **Do not ship the proposal.** The worker/pool bump does not fix the root cause (blocking I/O blocks the event loop, not worker starvation) and wastes resources on a 6-core machine. The Redis caching is acceptable as a temporary band-aid to reduce load, but it is not a substitute for fixing the three bottlenecks (blocking HTTP, N+1 user queries, missing index).