1. **Do not ship the on-call proposal.** Neither half works; both make the incident worse. Reasons in 2-3.
2. The Redis cache would never hit: `since` defaults to `datetime.now(timezone.utc)` computed per request, so the key `(org_id, since, limit)` is unique every call — 0% hit rate, and a warm cache still wouldn't stop the event-loop stall that pages you.
3. 16 workers × pool max 50 × 6 pods = 4,800 Postgres connections against a default `max_connections` of 100 — the DB starts refusing before this helps, and 4× the workers means 4× the per-process leaks, so OOM arrives sooner, not later.
4. Baseline before editing: `EXPLAIN (ANALYZE, BUFFERS)` the exact events SELECT with acme's params (`org_id=4127`, 30 d ago), and time the endpoint 5× warm at `limit=1000`; record median and spread.
5. The 1.4 s query has no usable index — only `actor_id` and `kind` are indexed, so the `org_id`/`created_at` predicate seq-scans 4.2 M rows and sorts them. Add `CREATE INDEX CONCURRENTLY events_org_created_idx ON events (org_id, created_at DESC)`.
6. The query returns every row in the window and Python slices afterwards — push `ORDER BY created_at DESC LIMIT $3` into SQL.
7. Dedupe is O(n²): `ev["dedupe_key"] in seen` scans a list per row — use a set, or do it in SQL.
8. Watch the interaction: applying `LIMIT n` before collapsing `dedupe_key` returns fewer than n items, so dedupe belongs in SQL (`DISTINCT ON (dedupe_key)` subquery, then order and limit) to keep full pages.
9. `serialize_event` awaits one `users` SELECT per event, sequentially — up to 1,000 round trips per request. Join `users` into the main query, or fetch actors in one `WHERE id = ANY($1)` batch.
10. This is what pages you: `requests.get` is a blocking sync call inside an async handler, up to 2 s per uncached IP and up to 1,000 IPs per request, so the whole worker (including `/healthz`) stops for seconds and the 3 s liveness probe kills the pod. Drop `location` from the list response and resolve geo on the detail view, or use an async client with bounded concurrency.
11. Only after 10 is fixed, consider a longer liveness timeout or a dedicated probe path — raising it first just hides the stall.
12. Main memory leak: `_request_timings` appends one float per request forever, ~30 req/s per worker across all routes, and nothing ever trims it — replace with a fixed-size ring buffer or a histogram.
13. `/internal/metrics` calls `sorted()` on that entire list synchronously, so it becomes a second, steadily worsening event-loop stall — the ring buffer or histogram fixes this too.
14. Second leak: `_geo_cache` is keyed by IP with no bound or eviction — give it an LRU cap and TTL, or move it to Redis.
15. `count` reports the page length, not the window total; the mobile client can't tell there's more.
16. Re-run step 4's exact measurement, then the correctness suite — dedupe ordering (newest wins), null actor, null `client_ip`, empty result — before calling it fixed.
17. Then fix the real cause of `limit=1000`: there's no pagination. Add a keyset cursor on `(created_at, id)` so the client stops asking for the whole window.