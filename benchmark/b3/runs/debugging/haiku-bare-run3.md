1. Cache persists indefinitely after first load, never re-reading the file — remove caching entirely, or detect file modification (via mtime or file watcher) and invalidate cache.
2. mtime checking won't work — filesystem granularity (coarse, platform-dependent) and float precision mean rapid changes are missed.
3. TTL-based expiry won't work — stale data is still returned to callers within the expiry window.
4. Optional reload parameter won't work — makes it too easy for callers to forget, leaving it optional rather than fixing the architectural problem.