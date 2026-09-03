1. N+1 user queries: serialize_event independently fetches one user per event (~1000 round-trips) → batch into one query.
2. O(n²) dedupe: checking `in seen` on a list for 1.9k events → use set.
3. Missing DB index: query does full table scan of 4.2M rows for ~1.9k result → create (org_id, created_at DESC) index.
4. Blocking geo lookups: requests.get() in async handler stalls event loop, breaks /healthz → use async httpx.AsyncClient.
5. Unbounded geo_cache: no eviction, grows to 2.1GB in 20h → add LRU or size-limit eviction.
6. Deploy DB index immediately (~40% latency reduction on query).
7. Fix dedupe: change `seen` from list to set.
8. Batch user lookups: one query instead of 1000, saves ~5 seconds.
9. Make geo lookups async with httpx and concurrent gather.
10. Add geo_cache eviction policy.
11. No: proposal doesn't fix root causes (N+1 queries, blocking I/O, missing index, unbounded memory); spend resources on fixes 1–10 instead.