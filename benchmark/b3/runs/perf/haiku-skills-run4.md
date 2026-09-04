1. Measure baseline: p95 11.2s for acme (org 4127) via Datadog; re-measure after each fix to confirm impact.
2. Events SELECT (1.4s, 12% of total) is slow due to missing index on org_id — create `CREATE INDEX CONCURRENTLY events_org_id_created_at_idx ON events (org_id, created_at DESC);`
3. N+1 user queries in serialize loop (1000 sequential fetches, 45-89% of total time) — prefetch all users in one query with `WHERE id = ANY($1)` and map by ID.
4. requests.get() is synchronous and blocks event loop (why healthz hangs) — replace with httpx.AsyncClient().get().
5. Unbounded _geo_cache dict causes memory leak (310MB → 2.1GB / 20h) — replace with `functools.lru_cache(maxsize=10000)`.
6. Dedup membership test on list is O(n²) — change `seen` to a set for O(1) lookup.
7. **DO NOT SHIP on-call's proposal**: worker bump and Redis caching mask the actual bottlenecks (missing index, N+1 queries, sync I/O, unbounded cache) and do not fix the memory leak; apply the fixes above first, then measure before scaling.