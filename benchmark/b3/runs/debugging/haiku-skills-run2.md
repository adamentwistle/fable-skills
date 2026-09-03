1. Cache is populated once and never invalidated regardless of file changes on disk; store the file's modification time when caching and reload if `os.path.getmtime()` is newer than the cached timestamp.

2. Default `path` parameter is hardcoded on first call, so calling `get_config('/other/path')` later still returns the original cached value; include `path` in the cache key (e.g., `_cache = {path: data}`).

**Tempting fixes that don't work:**
- Removing the cache entirely (works but defeats caching purpose).
- Re-reading on every call (defeats caching).
- Adding a `force_refresh` parameter (just moves the problem to the caller).
- Checking file existence (doesn't detect content changes, only deletion).