<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: s-dbg-skills-2. Content below the line is the agent's final output, unmodified. -->

---

1. Root cause: `_cache` is populated once and never checked against the file's actual state — the guard is "have we ever loaded" not "is this still current" — fix: track the file's mtime/hash alongside `_cache` and reload whenever the on-disk value differs, not just when `_cache is None`.
2. Non-fix (TTL): reloading every N seconds narrows the staleness window instead of eliminating it — still returns stale data within the window and does unnecessary reloads when the file hasn't changed.
3. Non-fix (always re-read, drop cache): removes staleness by removing caching entirely — hides the invalidation problem rather than solving it, sacrificing the caching benefit the function was written for.
4. Non-fix (manual `clear_cache()`/reset hook): pushes invalidation onto every caller remembering to call it — the bug is that the code itself doesn't detect change, so this doesn't fix the defect, it relocates it.
5. Secondary bug: cache ignores the `path` argument, so `get_config('a.json')` then `get_config('b.json')` returns `a.json`'s cached data — fix: key the cache by resolved path (or invalidate whenever requested path ≠ cached path).
6. Edge case: missing file / invalid JSON on (re)load raises unhandled inside the function with no defined recovery — fix: explicitly decide/document behavior on read failure (propagate vs. keep last-good cache), don't let it silently succeed with stale data.
7. Edge case: `get_config()` returns the live `_cache` dict object, so a caller mutating the returned dict corrupts the shared cache for every subsequent caller — fix: return a deep copy or an immutable view.
8. Edge case: no locking around load/reload — concurrent calls during a reload can race (partial read, double-read) — fix: guard the load/reload path with a lock if used from multiple threads.
9. Repro/verify: call `get_config()`, edit `config.json`, call `get_config()` again — pre-fix returns the original dict unchanged (falsifiable proof of staleness); post-fix, assert the second call's content matches the edited file (driven by mtime/hash comparison, not elapsed time).
