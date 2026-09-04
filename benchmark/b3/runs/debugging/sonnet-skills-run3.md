1. `_cache` is populated once and never invalidated — module-global memoization treats a mutable file as immutable state. Fix: re-read on each call, or key/invalidate the cache on the file's mtime.

2. Tempting fix "just don't use a global" (e.g. move `_cache` into a class instance) — doesn't help, the instance would go stale the same way; the bug is missing invalidation, not scope.

3. Tempting fix "clear `_cache` on every call before checking" — defeats the purpose of caching entirely; not what's being asked for (a cache with correctness), just brute-force removal of caching.

4. Tempting fix "reduce polling/restart interval" or infra-level restarts — masks the bug, doesn't fix `get_config()` itself.

5. Correct fix: check `os.stat(path).st_mtime` against a stored last-seen mtime each call; reload and update both `_cache` and the stored mtime only if it changed.