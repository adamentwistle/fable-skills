**ROOT CAUSE:** The `_cache` variable, once loaded, is never revalidated against the file on disk. The condition `if _cache is None` fires only once; subsequent calls skip the reload entirely, returning stale cached values even when the file changes.

**FINDINGS:**

1. Cache is never invalidated when file changes on disk — check file modification time and reload if mtime is newer than cached-load time.
2. Path parameter is ignored after the first call — use `path` as part of the cache key or reject subsequent calls with differing paths.

**TEMPTING FIXES THAT DON'T WORK:**

- TTL timer: reloads only after a timeout expires, not when the file actually changes.
- File existence check: detects only whether the file exists, not whether it was modified.
- External invalidation function: requires caller coordination; does not auto-detect changes.
- Write-through API: does not detect changes made by other processes.