<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: s-dbg-bare-3. Content below the line is the agent's final output, unmodified. -->

---

1. Root cause — the `if _cache is None` check only guards the *first* load and never re-validates against disk; fix: record the file's mtime (or hash) at load time and reload whenever it changes.
2. Tempting fix: TTL / re-read every N seconds — inadequate: still serves stale data inside the window and doesn't actually confirm the file changed.
3. Tempting fix: add a manual `invalidate()`/`clear_cache()` for callers to call — inadequate: shifts the burden to callers remembering to call it; an external edit to the file still won't be picked up automatically.
4. Tempting fix: just delete the caching and always `open()`+`json.load()` — inadequate: "fixes" staleness but defeats the purpose of caching (disk I/O + parse on every call).
5. Tempting fix: move `_cache` from module-global to an instance attribute (drop the `global` keyword) — inadequate: pure refactor, no invalidation logic added, same staleness persists.
6. Tempting fix: reload only when `open()`/`json.load()` raises an exception — inadequate: silent content changes (no error) still return the old cached dict.
7. Secondary gap once mtime-check is added: no locking around the reload, so concurrent callers can race on read-then-write of `_cache` — fix: guard the reload with a lock if used from multiple threads.
