1. Root cause: the cache is populated once and nothing ever records or re-checks the file's state, so a change on disk is undetectable — fix by stat-ing the file on every call and reloading when the stamp differs.
2. Store the freshness stamp next to the value: `st_mtime_ns` plus `st_size` (add `st_ino`/`st_dev` to survive atomic replaces), compared each call.
3. `path` is ignored after the first call — a second caller with a different file gets the first file's data; key the cache dict by resolved absolute path.
4. Reload can expose a half-written file: only assign the new value after `json.load` succeeds, keeping the previous one on error, and have writers use `os.replace`.
5. Concurrent first calls double-load and can tear during reload; guard the load with a module-level `threading.Lock`.
6. The shared mutable dict is handed to every caller, so one mutation silently rewrites everyone's config; return a copy.
7. Not a fix — TTL/time-based expiry: bounds staleness instead of removing it, still serving old values inside the window.
8. Not a fix — second-resolution `st_mtime`: misses same-second rewrites, which is exactly the edit-and-rerun case; use `st_mtime_ns` + size.
9. Not a fix — an `invalidate_cache()` helper or global reload flag: moves correctness onto every caller and writer remembering to call it.
10. Not a fix — `functools.lru_cache` or `if not _cache:`: the first has identical never-invalidated semantics, the second only changes behavior for an empty `{}` config (re-reads every call) and leaves staleness untouched.
11. Works but costly — deleting the cache: correct, at one read plus parse per call; fine only if the call rate is low.