1. **Do not ship the on-call proposal.** Neither half addresses the cause, and part 1 makes it worse: 16 workers × 50 conns × 6 pods = 4,800 Postgres connections (default `max_connections` is 100), and 4× the workers means 4× the leaking process. Redis at 60 s doesn't help either — the pod dies from a leak on *all* routes, not from this route's repeat reads, and cold-cache requests still stall the pod exactly as they do now.

2. Baseline first: `EXPLAIN (ANALYZE, BUFFERS)` the events SELECT with acme's parameters, and time the handler in three parts (SQL, actor lookups, geo lookups) for org 4127 at limit=1000, median of 5 runs. The slow log accounts for 1.4 s of a 6.4 s p50; the other ~5 s is currently unattributed and I'd expect it in the two loops below.

3. **The pager is `requests.get` in `lookup_geo`, called from async code.** It is a synchronous blocking call, so it freezes the whole worker's event loop — every other request on that worker, including `/healthz`, waits. Up to 1,000 uncached IPs × 2 s timeout per request explains the 3 s probe timeout and the 14 restarts. Fix: `httpx.AsyncClient` with a shared client and bounded concurrency.

4. **The RSS climb is `_request_timings`.** The middleware appends one float per request forever, on every route: 120 req/s × 20 h ≈ 8.6M entries per pod, and `/internal/metrics` then makes a full sorted copy on the event loop. Fix: `collections.deque(maxlen=...)` or a fixed-size histogram; keep the `/internal/metrics` shape.

5. **`_geo_cache` is a second unbounded cache** keyed on client IP with no eviction — bound it (LRU with a max size) and give it a TTL.

6. **No index serves the query.** `events` has 4.2M rows and indexes only on `actor_id` and `kind`, so `WHERE org_id = $1 AND created_at >= $2 ORDER BY created_at DESC` is a full scan plus a sort. Add `CREATE INDEX CONCURRENTLY events_org_created_idx ON events (org_id, created_at DESC);` — this is the 1.4 s.

7. **The actor lookup is an N+1**, one `SELECT ... FROM users` per event, awaited sequentially — 1,000 round trips for a mobile request. Fix: collect `actor_id`s after dedupe and fetch once with `WHERE id = ANY($1)`, then map in memory.

8. **The dedupe uses a list for membership**, so `ev["dedupe_key"] in seen` is O(n²) — ~1.8M comparisons at acme's 1,912 rows. Fix: a `set` alongside the list; identical behaviour, keeps first-seen (newest) order.

9. **The query has no `LIMIT`**, so it reads and transfers every row and every `payload` JSONB in the 30 d window before Python slices to `limit`. Push the dedupe down with `DISTINCT ON (dedupe_key)` ordered `dedupe_key, created_at DESC`, re-sort by `created_at DESC` in an outer query, and `LIMIT $3` there — note you cannot simply add `LIMIT` to the current query, because dedupe currently runs across the whole window and would silently return fewer than `limit` items.

10. Re-run step 2's measurement after each change separately, and revert any that doesn't move the number.

11. Then re-check the geo calls: with 6–9 fixed, if geo is still a large share, cache negative lookups too and consider dropping `location` from the list response entirely — it is per-event enrichment on a feed endpoint and may not be worth a network call at all. Confirm with the mobile team whether the Activity tab renders it.

12. Only after the above, revisit pool sizing with a real number: 4 workers × 10 conns × 6 pods = 240 is already over a default `max_connections`, so check the actual Postgres limit and whether a pgbouncer sits in front before touching either figure.

13. Add a regression guard: a test that hits the route against a seeded org with ~2,000 events and asserts a single actor query and no full-table scan, so the N+1 doesn't come back.

14. Unverified: the split of the remaining ~5 s between actor N+1 and geo calls, and whether `_request_timings` alone accounts for the full 310 MB → 2.1 GB (it is the only per-request unbounded growth I can see, but `_geo_cache` and the `sorted()` copy add to it). Step 2 settles both.