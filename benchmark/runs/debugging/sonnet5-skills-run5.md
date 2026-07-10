<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: s-dbg-skills-5. Content below the line is the agent's final output, unmodified. -->

---

1. `_cache is None` is a permanent "loaded" flag with no invalidation signal — root cause: once set, nothing ever compares cache state to disk state again → fix: load based on a freshness check (mtime/hash) against disk, not a null-check, on every call (or on an explicit invalidate hook), re-reading only when the file has changed.
2. Tempting fix "add a TTL and re-load after N seconds" — symptom-patch, not root cause: still serves stale data within the window and does unnecessary re-reads when nothing changed; masks rather than fixes the missing change-detection.
3. Tempting fix "just always re-read the file on every call" — removes the cache guard entirely rather than fixing it: correctness improves but the fix is "delete the cache," not "fix the invalidation," and reintroduces disk I/O on every call (defeats the purpose of caching) — call it out explicitly as an acceptable *only if caching isn't actually needed*, not a cache fix.
4. Module-level `global _cache` is shared mutable state with no lock — concurrent calls during the reload window can interleave a partial read with a stale return (or double-read); fix: guard load/reload with a lock (or an atomic reference swap).
5. No error handling on `open`/`json.load` — a missing file or invalid JSON on first call leaves `_cache` `None` forever, and on a reload-check design, a transient bad read would clobber a previously good cache; fix: only replace `_cache` after a successful parse, keep the old value on failure.
6. `get_config()` returns the same dict object on every call — a caller mutating the returned dict corrupts the shared cache for all future callers; fix: return a copy (or make it immutable) rather than the live reference.

Falsifiable cause: "get_config caches on first call via `_cache is None` and never compares against the file's current state again, so any edit to config.json after the first call is invisible until the process restarts (which resets `_cache` to `None`)." Reproduce: call `get_config()`, edit config.json, call again, assert the returned dict is unchanged; re-verify by repeating the same steps after adding mtime/hash-based invalidation and confirming the second call reflects the edit.
