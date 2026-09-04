1. Cache never revalidates against source; `_cache is None` checks only if cache was populated, not if file changed. **Correct fix:** Track file mtime with `os.stat(path).st_mtime` and reload if it differs from last-known value.

2. TTL expiration won't work; stale reads still occur within the expiration window. **Wrong because:** Bounded staleness is not correctness; file changes within the window are still missed.

3. Exception handling won't work; file modifications don't raise exceptions. **Wrong because:** Proactively checking file state is required; catching errors only catches errors.

4. Optional `reload` parameter won't work; leaves default behavior broken. **Wrong because:** Callers who don't pass `reload=True` still get stale data; the bug persists silently.

5. Removing `global _cache` won't work; the cache still persists in the function's local scope. **Wrong because:** The persistence model is the problem, not the keyword; scope doesn't change when revalidation is needed.

6. Remove caching entirely (reload every call); simplest fix if performance permits. **Why it works:** No cache = no stale data; guarantees freshness on every call.