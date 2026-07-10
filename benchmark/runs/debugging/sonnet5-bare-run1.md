<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: s-dbg-bare-1. Content below the line is the agent's final output, unmodified. -->

---

1. Cache is populated once and never invalidated — root cause is the `if _cache is None` guard never re-checks the source; fix by comparing the file's mtime/hash on each call and reloading when it changes (or removing the cache entirely).
2. Tempting fix "just remove the `is None` check and always reload" fixes staleness but reintroduces a disk read on every call — acceptable only if I/O cost is fine, otherwise pair with mtime-based invalidation instead.
3. Tempting fix "add a TTL (e.g., reload every 60s)" does NOT address root cause — it masks staleness with a delay rather than detecting the actual change, so edits can still be missed or picked up late.
4. Tempting fix "call `get_config()` differently / clear `_cache` manually after edits" does NOT work in general — it only helps if the same process that edited the file also calls the clearer; external edits (another process, deploy, manual edit) are still missed.
5. Module-level global `_cache` is not thread-safe — concurrent first-calls can race on the read/parse; fix by guarding with a lock (or lazy-init pattern) regardless of the staleness fix.
6. `path` is accepted as a parameter but the cache key ignores it — calling with a different path still returns the first-loaded config; fix by keying the cache dict on `path`.
