1. Add compound index events(org_id, created_at DESC) — query scans 4.2M rows for ~2k matches; index will cut query time from 1.4s to <100ms.
2. Replace blocking requests.get() in lookup_geo() with httpx async client — currently blocks event loop for 200-500ms per miss, causing /healthz timeouts and liveness probe restarts (that's what pages you).
3. Replace unbounded _geo_cache dict with functools.lru_cache(maxsize=10000) — dict grows without limit; this is the memory leak (310MB→2.1GB).
4. Change deduplication from O(n²) list scan to set lookup — cheap win, one-line fix.
5. Parallelize serialize_event calls with asyncio.gather() — multiple user+geo fetches can run concurrently instead of sequentially.
6. Limit the results query to LIMIT {limit} since you only serialize that many anyway — avoid fetching and deduping 2k rows when you discard most.
7. Do NOT ship the proposal as-is: worker increase (4→16) masks the blocking call without fixing it; pool increase (10→50) doesn't address the slow query; only the Redis cache has value, but it shouldn't replace root-cause fixes. Deploy the index first, then reassess whether caching is needed.