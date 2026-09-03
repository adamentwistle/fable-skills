1. Root cause: the cache is never invalidated — it is filled on first call and never compared against the file again, so only a restart can change it; fix by recording the file's stat signature at load time and reloading when it differs.
2. The signature must be content-sensitive, not just `st_mtime`: store `st_mtime_ns` + `st_size` (+ `st_ino`) and treat any difference as stale.
3. The cache ignores `path` — a second call with a different file returns the first file's data; fix by keying a dict on the resolved absolute path.
4. The cached dict is returned live, so one caller's mutation silently rewrites config for everyone; fix by returning a deep copy.
5. Concurrent first calls race on `_cache` and each parse the file; fix with a module-level lock around the load-and-store.
6. A reload that hits a partial write or bad JSON raises and can leave the cache half-updated; fix by parsing into a local and swapping in only on success.
7. NOT a fix — a TTL: still serves known-stale data for the whole window and leaves the missing invalidation in place.
8. NOT a fix — `functools.lru_cache`: identical permanent memo, just keyed by path.
9. NOT a fix — exposing `reload()` or setting `_cache = None` at call sites: pushes correctness onto every caller and misses out-of-band edits.
10. NOT a fix — `if not _cache` instead of `is None`: changes only the empty-config case, staleness untouched.
11. NOT a fix — an inotify/watchdog file watcher: heavier, and blind to edits while it's down or on network/container mounts; a stat on each read is the cheap correct check.