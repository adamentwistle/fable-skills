1. **DO NOT SHIP** the on-call proposal — more workers/pool doesn't fix the N+1 queries or blocking I/O that are the real bottlenecks; caching helps latency on hits but doesn't stop the memory leak or pod restarts.

2. Finding: Missing index on (org_id, created_at DESC) causes full table scan of 4.2M rows; this index explains the 1.2–1.6s baseline query time — add it.

3. Finding: N+1 query in serialize_event loop — each event fetches a user separately; 1.9k events = 1.9k DB round-trips — batch-fetch all users in one WHERE id IN query.

4. Finding: Blocking requests.get() in lookup_geo stalls the event loop, causes /healthz timeout, triggers pod restarts — replace with httpx async client.

5. Finding: Unbounded _geo_cache dict accumulates IPs over time; explains memory climb from 310 MB to 2.1 GB over 20 h — bound to 10k entries with LRU eviction.

6. Finding: Unbounded _request_timings list grows with every request — cap to recent 10k entries to limit memory.

7. Add migration: CREATE INDEX events_org_id_created_at ON events (org_id, created_at DESC).

8. Batch-fetch users: prefetch all actor_ids in one WHERE id IN query, store in a dict, hydrate serialize_event from that dict instead of per-event queries.

9. Replace requests.get() with httpx async client in lookup_geo; implement LRU cache (maxsize=10k) for geo data to unblock event loop.

10. Cap _request_timings: add `_request_timings = _request_timings[-10000:]` in middleware on each append to bound memory.

11. Verify: measure p50/p95 latency for orgs 4127 and 88 via Datadog dashboard post-deploy to confirm fixes.