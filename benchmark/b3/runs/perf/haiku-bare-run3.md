1. **Don't ship the proposal** — scaling workers and pool sizes merely buffers slow requests; the real issues (missing index, N+1 actor queries, unbounded geo cache) cause the slowness and must be fixed first.

2. Add composite index on `events(org_id, created_at DESC)` — the SELECT query drops from 1.2–1.6s to ~50ms; this is the critical fix.

3. Cap `_geo_cache` to a max size with a check before insertion — prevents memory from growing unbounded; currently leaks from 310MB to 2.1GB over 20h.

4. Batch actor lookups — replace 1000 sequential `fetchrow()` calls per request with a single `SELECT...WHERE id = ANY($1)` query.

5. Parallelize serialization — replace `[await serialize_event(...) for ...]` with `asyncio.gather(...)` to run serialization concurrently instead of sequentially.

6. After the above land, re-benchmark; if still slow, revisit the scaling proposal.