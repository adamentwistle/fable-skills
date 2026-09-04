1. N+1 query on users table — serialize_event does conn.fetchrow() per event (1,912 calls for acme); batch-fetch actors with WHERE id IN (...) and build a lookup dict.

2. Missing index on (org_id, created_at) — event query scans full table; CREATE INDEX events_org_id_created_at_idx ON events(org_id, created_at DESC).

3. Unbounded _geo_cache per worker — module-level dict grows without eviction, contributing to RSS climb from 310MB to 2.1GB over 20h; switch to functools.lru_cache(maxsize=10000).

4. Unbounded _request_timings list — module-level list appends every request forever, contributing to memory leak; cap at last 10000 entries or clear every 5 minutes.

5. Dedup inefficiency — O(n²) list lookups on `if ev["dedupe_key"] in seen`; use set instead.

6. **Do not ship on-call proposal.** N+1 is the root cause of 6-12s latency; bumping workers/pool/cache are band-aids that don't fix it. Ship fixes 1-5 first, re-measure with Datadog (expect p95 to drop from 11.2s to <2s for acme), then evaluate if Redis caching is needed.