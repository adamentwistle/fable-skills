1. Root cause: `_cache` is populated once and never invalidated — module-level memoization with no expiry, so disk changes are invisible until process restart.
2. Tempting non-fix: adding a TTL/short cache timeout — masks the bug, still serves stale data within the window and adds latency/complexity.
3. Tempting non-fix: clearing `_cache` manually elsewhere in code — relies on every writer remembering to do it; misses external edits to the file.
4. Tempting non-fix: just removing the cache (read file every call) — works but reintroduces disk I/O on every access; fine only if call frequency is low.
5. Correct fix: cache keyed by file mtime (or hash), reload when `os.path.getmtime(path)` changes — cheap staleness check, no polling needed.
6. If sub-process/multi-writer or near-real-time freshness matters: use a filesystem watch (e.g. watchdog/inotify) to invalidate `_cache` on change instead of polling mtime per call.