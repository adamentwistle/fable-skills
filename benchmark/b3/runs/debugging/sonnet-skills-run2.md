1. Cache never invalidated once set — `_cache is None` only true before first load — fix: cache keyed/checked against file mtime (or hash), reload when it changes.
2. `path` parameter ignored after first call — a second call with a different path still returns the first file's cached data — fix: key the cache by `path`, not a single global.
3. No file-change detection at all — fix: stat the file each call and compare mtime/size (or just always read; cheap for config files) before deciding to reuse the cache.

Tempting fixes that don't work:
- Just calling `get_config()` again after editing the file — no-op, `_cache` is already set, still stale.
- Reducing a TTL/adding a timer-based refresh — masks the bug, still serves stale data between refreshes and doesn't fix multi-path case.
- Making `_cache` non-global / instance attribute — doesn't address staleness, same bug at instance scope.
- `os.path.exists(path)` check — existence isn't change; file can exist and still have stale content in cache.