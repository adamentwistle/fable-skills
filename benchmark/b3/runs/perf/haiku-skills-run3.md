1. Missing index on (org_id, created_at DESC) causes full scan of 4.2M events instead of 1.9k (1.2–1.6 s per slow query); create this index.

2. N+1 actor queries in serialize_event loop: 1000+ lookups per response for limit=1000; batch all actors in single WHERE id IN query.

3. Blocking requests.get() in geo lookup holds event loop during 2 s timeout, stalls all workers and causes /healthz probe timeouts; replace with async httpx.AsyncClient.

4. Unbounded _request_timings list: 120 req/s × 20 h = 8.6M floats ≈ 69 MB per worker; implement ring-buffer or periodic clear.

5. Unbounded _geo_cache: grows with every new IP, no eviction; add TTL or LRU eviction policy.

6. Dedupe logic is O(n²): O(n) list lookup per iteration; change seen from list to set.

7. **Do not ship proposal.** Root causes are missing index + N+1 queries (not concurrency limits). Bumping workers/pool will worsen memory leak; caching hides the problem. Deploy index first (zero-downtime), then batch N+1 + async HTTP + fix caches, re-measure with Datadog (expect 10–100× speedup), then revisit caching only if needed.