1. Add index events(org_id, created_at DESC) — query is 1.2-1.6s from full table scan
2. Batch actor fetches with WHERE id IN — N+1 query per event
3. Replace sync requests.get() with async httpx in lookup_geo — blocks event loop, stalls healthz
4. Clear _request_timings periodically — unbounded list = ~240MB/20h memory leak
5. Cap _geo_cache with functools.lru_cache(maxsize=...) — unbounded cache leaks memory
6. No: reject on-call proposal; worker bumping worsens blocking I/O — implement 1-5 first, optionally add Redis cache