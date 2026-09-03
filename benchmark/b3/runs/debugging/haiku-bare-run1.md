1. Cache never invalidates once `_cache` is non-None; fix by checking file modification time and re-reading if mtime changes.

2. Tempting wrong fix (remove cache entirely)—solves staleness but kills performance benefit of caching; use state-tracked invalidation instead.

3. Tempting wrong fix (add timeout/TTL expiration)—arbitrary delay doesn't detect actual file changes, just masks the problem; track real file state.

4. Tempting wrong fix (ignore the `path` parameter)—if `path` changes between calls, stale config from a different file gets returned; either cache per-path or validate that path hasn't changed before using cached value.