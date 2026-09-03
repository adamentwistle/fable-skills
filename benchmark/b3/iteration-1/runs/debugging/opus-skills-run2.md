1. Root cause: `_cache` is filled on first call and never re-checked against the file, so nothing can ever invalidate it — fix by stat'ing the file each call and reloading when it changed.
2. The staleness check must be a file-identity fingerprint, not a timer — cache `(st_mtime_ns, st_size, st_ino)` alongside the data and reload on mismatch.
3. `path` is ignored by the cache — a second call with a different path returns the first file's data; key the cache by the resolved absolute path.
4. NOT a fix: a TTL/expiry — it still serves stale values for the whole window and re-reads when nothing changed.
5. NOT a fix: an explicit `clear_cache()` for callers to invoke — external edits (deploy, editor, another process) never call it, which is the reported case.
6. NOT a fix: `if not _cache` instead of `is None` — only changes behavior for an empty config, causing a re-read every call.
7. NOT a fix: a lock around the load — removes a race, not the staleness.
8. NOT a fix: returning `copy.deepcopy(_cache)` — stops caller mutation leaking, unrelated to disk changes.
9. NOT a fix: `functools.lru_cache` — same never-invalidated cache, just per-path.
10. Second-resolution `st_mtime` alone misses same-second rewrites — use `st_mtime_ns` plus size, and read-then-parse so a partially written file raises instead of poisoning the cache.