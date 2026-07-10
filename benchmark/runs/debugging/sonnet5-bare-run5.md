<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: s-dbg-bare-5. Content below the line is the agent's final output, unmodified. -->

---

1. Root cause: `_cache` is populated once and reused forever with no invalidation logic tied to the file's actual state — fix by checking the file's mtime (or hash) on each call and reloading when it changes.
2. Cache key ignores `path` — a second call with a different path still returns the first path's cached data — fix by keying `_cache` on `path`.
3. Tempting fix "add a TTL / poll every N seconds" does NOT fix it — it only narrows the staleness window, edits within the TTL are still missed and it adds arbitrary latency.
4. Tempting fix "just remove the `if _cache is None` check and always reload" does NOT fix it — it defeats the purpose of caching (reads/parses the file on every call) rather than reloading only when changed.
5. Tempting fix "make `_cache` an instance attribute instead of global" does NOT fix it — it's an encapsulation change, not a staleness fix; the object still never re-checks the disk.
6. Tempting fix "expose a manual `reload_config()` function" does NOT fix it — it shifts the burden to every caller remembering to invoke it, so drift/staleness bugs will recur.
7. Edge case even with mtime-check fix: concurrent writers/partial writes can cause a read mid-write — fix by reading via atomic write pattern (temp file + rename) on the writer side, or wrap the read in a retry/backoff.

---
No model-suitability note needed — Sonnet 5 without extended thinking is appropriate for this scoped code-diagnosis task.
