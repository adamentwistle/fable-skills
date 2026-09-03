1. Root cause: `_cache` is filled on first call and never checked against the file again, so any on-disk edit is invisible for the process lifetime — record the file's `stat()` (`st_mtime_ns`, `st_size`) with the data and reload when it differs.
2. The cache ignores `path`, so a second call with a different file returns the first file's contents — key the cache dict by the resolved absolute path.
3. Two threads can enter the load (and, once reloading is added, swap `_cache` mid-read) — guard the stat-check-and-load with a `threading.Lock`.
4. `st_mtime` alone can miss a same-tick rewrite on coarse-timestamp filesystems — compare `st_mtime_ns` plus `st_size`, or hash the bytes when you need certainty.
5. Callers get the shared mutable dict, so one caller's mutation silently becomes everyone's config and survives until reload — return a deep copy or a read-only mapping.
6. A config rewritten in place can be read half-written, caching a partial parse or raising — catch `JSONDecodeError`, keep the last good value, and have writers write-temp-then-`os.replace`.
7. NOT a fix — a TTL/time-based expiry: it only shrinks the stale window and still re-reads when nothing changed; staleness remains by design.
8. NOT a fix — adding a `reload_config()` for callers to call: depends on every writer remembering, and does nothing when an editor or another process edits the file.
9. NOT a fix — `functools.lru_cache` on `get_config`: it fixes the path-keying bug only and is still never invalidated by file changes.
10. NOT a fix — deleting the cache entirely: correct but re-parses on every call, and still leaves the shared-mutable and torn-read problems (6, 5) untouched.