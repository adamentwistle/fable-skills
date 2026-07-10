<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: s-dbg-skills-4. Content below the line is the agent's final output, unmodified. -->

---

1. Root cause: `if _cache is None` never re-fires after the first successful load — nothing on disk-write, mtime, or hash ever invalidates `_cache` — fix: check the file's mtime/hash each call and reload when it differs from what's stored (invalidation keyed to actual on-disk state), not a bare permanent flag.
2. Symptom-patch (reject): TTL-based expiry — still serves stale data for the whole window and reloads on a schedule unrelated to when the file actually changed.
3. Symptom-patch (reject): always re-reading the file on every call — "fixes" staleness by deleting the cache, not by fixing invalidation; defeats the purpose of caching if perf mattered.
4. Symptom-patch (reject): a manual `clear_cache()`/`reload()` escape hatch alone — only helps if every caller who changes the file remembers to call it; doesn't fix the get-path.
5. Real correctness bug: `path` argument is ignored once `_cache` is set — calling `get_config('other.json')` after the first call silently returns the first file's data — fix: key the cache by path (or store path+mtime alongside the cached dict) and compare on each call.
6. Real correctness bug: the same dict object is returned every call — any caller mutating the returned config corrupts state for all future callers — fix: return a copy (or use an immutable/frozen structure).
7. Concurrency: check-then-load on `_cache is None` is not locked — benign today since reassignment is atomic, but a reload-on-mtime-change fix must guard the "read mtime, read file, reassign" sequence with a lock or it can race under concurrent invalidation.
8. Edge case (already correct, don't break it): missing file/invalid JSON on first call raises and leaves `_cache` as `None`, so the next call retries — a naive try/except that caches `{}` on failure would regress this into permanently masking a real config error.
