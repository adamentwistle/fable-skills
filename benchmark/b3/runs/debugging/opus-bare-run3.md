1. Root cause: the cache is never invalidated — `_cache` is set once and no code path clears it, so disk changes are invisible for the process lifetime; fix by storing the file's mtime (and size) alongside the data and reloading when it differs.
2. Cache key ignores `path` — a second call with a different file returns the first file's data; fix by keying the cache dict on the resolved absolute path.
3. `if _cache is None` also re-reads on every call when the file legitimately holds `null` (or would, if a falsy check were used) — minor, but fix by using a sentinel object rather than `None` for "unset".
4. No thread safety — concurrent first calls can each load and race on assignment; fix by guarding the load with a module-level `threading.Lock`.
5. NOT a fix: adding a TTL/expiry timer — it only shortens the staleness window, still serves wrong values inside it, and reloads pointlessly when nothing changed.
6. NOT a fix: checking `os.path.exists` or catching `FileNotFoundError` — the file exists and reads fine; existence has nothing to do with the staleness.
7. NOT a fix: making the cache thread-local or per-request — every worker still caches forever, so the stale read reappears in each one.
8. NOT a fix: calling `f.flush()`/`os.fsync` on the writer side or reopening the file handle — the reader never reaches the open call once `_cache` is set.
9. NOT a fix: `functools.lru_cache` on the loader — it's the same never-invalidated memoization with a nicer name (though it would at least key on `path`).
10. Only if you need sub-mtime-resolution correctness: mtime can be coarse (1–2s on some filesystems) and a same-second rewrite can be missed; fix by comparing a content hash, or accept the window explicitly.