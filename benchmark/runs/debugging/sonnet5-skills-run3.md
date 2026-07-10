<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: s-dbg-skills-3. Content below the line is the agent's final output, unmodified. -->

---

1. Root cause: `_cache is None` only distinguishes "never loaded" from "loaded" — it has no notion of the on-disk file having changed, so a populated cache is treated as valid forever → fix: track the file's mtime (or hash) alongside the cached value and reload when that changes, not just when the cache is empty.
2. Tempting non-fix — TTL/periodic expiry: masks the symptom by shrinking the staleness window but doesn't detect actual changes; still serves stale data inside the TTL and reloads needlessly when nothing changed.
3. Tempting non-fix — always re-read the file on every call: "fixes" staleness by deleting the cache's purpose, reintroducing the I/O/parse cost the cache existed to avoid.
4. Tempting non-fix — external `clear_cache()`/manually setting `_cache = None`: pushes invalidation responsibility onto every caller instead of fixing that `get_config` itself can't detect staleness.
5. Edge case — missing/invalid file: no `FileNotFoundError`/`JSONDecodeError` handling; a reload-on-change fix must not let a bad re-read clobber a good cached value or crash callers that only wanted the last-known-good config.
6. Edge case — concurrent access: `_cache` (and any added mtime state) is mutated with no lock; concurrent calls during a reload can race and observe a torn (mtime, data) pair → guard the update with a lock or swap a single immutable tuple atomically.
7. Edge case — aliasing/mutation: the function returns the cached dict by reference, so any caller that mutates it corrupts the shared cache for every subsequent caller (a second, distinct staleness bug) → return a copy.
8. Edge case — mtime granularity: rapid successive writes within the same filesystem timestamp resolution (e.g., 1s) can leave mtime unchanged → compare (mtime, size) or a content hash if sub-second edits matter.
9. Repro: load config, call `get_config()`, edit `config.json` on disk, call `get_config()` again without restarting — old code returns old dict; verify fix by asserting the second call reflects the edit, and add a regression test that fails on current code and passes after the mtime/hash check is added.

Model suitability: reasoning effort was set to moderate (auto/40) for a request whose actual value is in exhaustively enumerating subtle edge cases (concurrency, aliasing, mtime granularity) and cleanly separating root cause from symptom-patches — a higher extended-thinking budget (or Opus) would more reliably surface all of these on the first pass rather than needing follow-up prompting.
