1. Create index (org_id, created_at DESC)—the 1.2–1.6s query is a full table scan.
2. Replace _geo_cache dict with functools.lru_cache(maxsize=10000)—unbounded dict grows to 2.1GB causing OOM.
3. Batch-fetch users in serialize_event with SELECT … WHERE id = ANY($1)—currently 1000+ separate queries per request.
4. Fix dedup to use set() instead of list—current code is O(n²).
5. Add Redis cache for (org_id, since, limit) responses, 60s TTL—reasonable temporary layer.
6. Do not ship the worker/pool bump proposal; the index will help far more than connection scaling.

**Proposal: No.** Ship the index, cache fixes, and batching instead. The Redis caching is appropriate.