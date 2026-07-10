<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: dbg-skills-2. Content below the line is the agent's final output, unmodified. -->

---

## Diagnosis: `get_config()` stale-cache bug

1. **Root cause** — the cache is gated only on `_cache is None`, so it is populated on the first successful call and *nothing* ever ties it to the file's current contents; no live code path can replace it, making process restart the only invalidator. Fix: key the cache to the file's `os.stat().st_mtime` (and size) and reload when it changes.

2. **Falsifiable cause statement** — "The value is stale because the cache is invalidated by *nothing but a null check*; if I re-key it on the file's mtime, editing config.json (new mtime) between two calls will return the new values with no restart." Repro: call `get_config()`, edit `config.json`, call again → old values; re-verify after fix with the same three steps → new values.

3. **Symptom-patch, NOT a real fix — TTL / expiry window**: still serves stale data for the whole window and re-reads pointlessly when the file is unchanged; it masks the missing invalidation instead of curing it.

4. **Symptom-patch, NOT a real fix — re-read on every call (drop the cache)**: "fixes" staleness but discards caching entirely and adds a file open + JSON parse per call; the real requirement is reload-*on-change*, not reload-always.

5. **Symptom-patch, NOT a real fix — manual `clear_cache()` / signal handler**: pushes the bug onto every call site, which now has to *know* when the file changed — the same missing-invalidation defect, relocated.

6. **Latent bug: `path` is ignored by the cache** — the global is path-agnostic, so a second call with a different `path` returns the *first* file's contents; fix by keying the cache dict on `path` (mtime check then subsumes it).

7. **Edge case — corruption after first success**: an mtime-triggered reload will raise on a now-invalid/removed file mid-run; decide explicitly to either propagate or retain the last-good value (silent retain is a trap — log it).

8. **Edge case — concurrency**: the `if _cache is None` check-then-set (and any mtime check-then-reload) races under threads; guard the read-stat-reload with a lock if the process is multi-threaded.

9. **Edge case — shared mutable object**: every caller gets the same dict, so one caller's mutation is seen by all and is silently discarded on the next reload; return a copy (or a frozen view) if caller isolation matters.

---

Model suitability: this is a small, reasoning-bounded diagnosis of a single snippet — **Sonnet with extended thinking would have been sufficient and more economical** than Opus 4.8 here; Opus is not wrong, just heavier than the task needs.
