1. Module-level `_cache` never invalidated once set — fix: check file mtime/hash each call and reload when it changes.
2. `_cache is None` sentinel means an empty/falsy config (`{}`, `null`) reloads every call — fix: use a separate `bool` flag ("loaded") instead of `is None`.
3. `path` param is ignored after first call (cache keyed by nothing) — fix: key the cache dict by `path`.
4. Not thread-safe (two threads can both see `_cache is None` and double-load, or one reads mid-write) — fix: guard with a lock.

Tempting fixes that don't work: adding a manual `clear_cache()` function (doesn't fix the "stale-until-someone-remembers-to-call-it" problem, silent by default); wrapping in `lru_cache` (same staleness, just a different cache); reducing a TTL or "reload every N calls" (masks the bug, still serves stale data for up to N calls/seconds); catching and ignoring file errors on reload (hides real failures, not the root cause).