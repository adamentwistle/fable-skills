1. Cache is populated once and never invalidated — fix by checking file mtime/hash each call and reloading when it changes, or removing the cache entirely.
2. Tempting fix "just clear `_cache` on a timer" doesn't work — a poll interval still serves stale data between ticks and adds needless complexity.
3. Tempting fix "reduce cache lifetime by calling `get_config()` more often" doesn't work — the cache itself never expires, so callers still get the first-loaded value forever.
4. Tempting fix "make `_cache` a local variable instead of global" doesn't work — it fixes cross-call staleness only by removing caching, defeating the point without addressing invalidation.
5. Global mutable `_cache` isn't thread-safe — concurrent reload should use a lock if this runs multi-threaded.
6. `path` is ignored after first call — a second call with a different path silently returns the first path's cached config; fix by keying the cache on path.