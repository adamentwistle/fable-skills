1. Do not ship the proposal: 16 workers × 50 conns × 6 pods is 4,800 Postgres connections, 4× more copies of the per-worker leak, and a 60 s Redis cache hides the bug without stopping the event-loop stalls that page you.
2. Confirm before touching code: `py-spy dump` an api worker mid-request (expect it parked in `requests.get`), and `EXPLAIN (ANALYZE, BUFFERS)` the events query with acme's params (expect Seq Scan over 4.2M rows).
3. Root cause of the stalls and restarts: `lookup_geo` calls synchronous `requests.get` inside an async handler, freezing the worker's event loop up to 2 s per uncached IP, up to ~1k times per request, so `/healthz` on that worker can't answer; switch to an async client, dedupe IPs first, fan out under a semaphore.
4. Leak 1: `_request_timings` is appended on every request and never trimmed (~120 req/s × 20 h ≈ 8.6M floats per worker, ×4 workers), and `/internal/metrics` sorts the whole list on the loop each call; replace with a bounded deque or a histogram.
5. Leak 2: `_geo_cache` is an unbounded per-worker dict keyed by client IP; bound it (LRU + TTL).
6. Missing index: nothing serves `WHERE org_id AND created_at >= ORDER BY created_at DESC`, hence 1.4 s per call; `CREATE INDEX CONCURRENTLY events_org_id_created_at_idx ON events (org_id, created_at DESC)`.
7. No LIMIT in SQL: every row in the 30 d window (with full JSONB payload) is fetched, deduped, then sliced in Python; dedupe in SQL (`DISTINCT ON (dedupe_key)` subquery) and push `LIMIT` down.
8. N+1: `serialize_event` runs one `users` lookup per event, awaited sequentially (~1k round trips per request); fetch all distinct actor_ids in one `WHERE id = ANY($1)`.
9. `seen` is a list, so dedupe is O(n²) with `in`; use a set (moot once step 7 lands).
10. Ship steps 3-9 as one PR plus the index migration; verify with a load test that `/healthz` answers in <100 ms while a 1k-event request is in flight, and that per-org p95 drops under ~300 ms.
11. Watch RSS on one canary pod for 24 h before rollout; it should stay flat near 310 MB.
12. Only after that, revisit caching if p95 still matters; it won't be needed for this bug.