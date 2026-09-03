1. The events table has no index on (org_id, created_at); the 1.2–1.6 s query time is a full table scan — add `CREATE INDEX events_org_created_idx ON events (org_id, created_at DESC)` immediately.

2. The code executes one SELECT query per event to fetch actor data (N+1); with 1k events, that's 1k additional queries — batch them with a single `WHERE actor_id IN (...)` query and a local dict lookup.

3. The `_geo_cache` dict grows unbounded and is the memory leak; after 20h it contains thousands of IPs and fills pod memory — cap it at ~1k entries with LRU eviction, or move to Redis with TTL.

4. The dedupe logic does `if ev["dedupe_key"] in seen` on a list, O(n) per check, quadratic overall — use a set instead.

5. `lookup_geo` is synchronous HTTP in an async context, blocking the event loop and starving /healthz; the 3 s timeout on liveness probes matches your observed hang duration — use an async HTTP client (httpx.AsyncClient).

6. Do not ship on-call's proposal; it adds workers and caching but leaves the root causes (missing index, N+1, memory leak, blocking I/O) intact — pod restarts and timeouts will continue until those are fixed.

7. Measure baseline latency (p50/p95/p99 for acme org 4127) before and after each fix to confirm the index drop-in gives 10–15× speedup, N+1 fix gives another 2–5×, and memory stabilizes.