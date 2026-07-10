<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Full blind-grader prompt (includes the answer key and the anonymized review summaries R1-R20 exactly as fed to the grader) for the debugging area, unmodified. -->

---

You are blind-grading 20 independent reviews (R1–R20) of the SAME debugging task. You know nothing about who or what produced them. Score objectively.

The task was: diagnose why `get_config()` returns stale values after the config file changes (a module-global `_cache` guarded by `if _cache is None`, loaded once via json.load), give the root cause and correct fix, and call out tempting non-fixes.

ANSWER KEY — 8 issue classes. Mark each review Y only if it genuinely identifies that specific point:
- A1 Root cause: cache populated once and never invalidated (no freshness/mtime/hash check); reload when file changes.
- A2 Rejects TTL/periodic-expiry as a proper fix (calls it a symptom-patch / staleness-window shrink).
- A3 Rejects "always re-read / drop the cache" OR "manual clear_cache()" as the proper fix (discards caching / relocates burden).
- A4 Secondary bug: the `path` argument is ignored after first call (cache not keyed by path).
- A5 Thread-safety / concurrency race (check-then-act on the global, or racy reload) → lock.
- A6 Shared mutable return: same dict handed to all callers, a caller mutating it corrupts the cache → return a copy.
- A7 Gives explicit REPRODUCE-and-verify steps (edit file between two calls, assert stale, re-verify fix).
- A8 The `is None` sentinel bug: a config of JSON `null` (or empty) makes `_cache` stay None so it reloads every call / never latches.

Output a markdown table: rows R1–R20, columns A1–A8 with Y/blank, plus a "Total /8" column. Then output the mean total for each of these four groups: R1–R5, R6–R10, R11–R15, R16–R20. Be strict and consistent.

===== REVIEWS =====
R1: RC _cache set once, `is None` never re-reads → key cache on file mtime/size, reload on change. stat file each call, compare mtime/size. `path` arg ignored after first call → key cache by path. Tempting-WRONG: time-based TTL only shrinks staleness window. Tempting-WRONG: mtime alone (1s res) misses same-second rewrite; pair with size/inode. Tempting-WRONG: drop cache/re-read every call removes caching and leaves path bug. Concurrency: check-then-act on global under threads races → guard with lock.

R2: RC unconditional memoization, no invalidation → invalidate on stat mtime_ns+size. Cache key ignores path → key by realpath. TTL is a tempting NON-fix (shrinks window). Bare mtime-equality weak (granularity/same-second rewrite) → mtime_ns+size. "Re-read every call" not intended (discards caching). Returned dict is shared mutable ref; callers mutating corrupt the cache → return copy/freeze. Check-then-set race under concurrency (two threads load twice) → lock.

R3: RC cache populated once, never invalidated; `is None` is the only reload trigger → key on mtime+size. process globals persist. `path` ignored (global not keyed by path) → key by path. Aliasing: shared dict returned by ref, caller mutation corrupts → deep copy. Tempting non-fix: `is None`→`if not _cache` cosmetic. Tempting: TTL masks not fixes. Tempting: "call more often"/document restart = no code change. Tempting: lru_cache same trap.

R4: RC `_cache` refilled only when None, stale forever → invalidate on stat mtime. No mtime/content check exists. Cache key ignores path → key by resolved path. Tempting-wrong: delete cache/always re-read discards caching. Tempting: lru_cache same stale bug. Tempting: fixed TTL still stale within interval. Tempting: importlib.reload = in-process restart. Tempting: move _cache to class = scoping only. Concurrency: check-then-reload race → lock.

R5: RC `_cache` permanent process-lifetime memo, `is None` fires once → invalidate on stat mtime. path not keyed → key by path. Returns shared mutable object → deep copy. Not thread-safe, concurrent first-callers double-load/race → lock. NOT-fix: TTL serves stale within window. NOT-fix: re-read every call abandons cache purpose. NOT-fix: manual reset_cache pushes bug to callers.

R6: RC + falsifiable statement: `is None` guard makes load one-time, cache carries no freshness key → gate reload on stat mtime. TTL would NOT fix (bounds window). Re-read-always NOT a fix (removes caching). Manual clear_cache NOT a fix (caller-dependent). Separate bug: cache keyed globally, path ignored → key by path. `is None` sentinel bug: JSON null loads to None, guard never latches, reloads every call → use distinct sentinel. Shared-mutable leak: same dict to all callers → deep copy. Concurrency: two threads see None, both load → lock. First-call failure path: missing/invalid file raises, _cache stays None (uncaught). REPRO: call, rewrite file, call, assert changed; assert unchanged file causes no re-read.

R7: RC refresh gated only on `is None` (flips once), no mtime stored. Falsifiable statement + REPRO: load, edit, call, assert stale; re-verify. TTL symptom-patch. Re-read-always symptom-patch (discards caching). Manual clear_cache symptom-patch. path ignored (global not keyed) → key by path. Edge: corruption after first success (reload raises on removed file). Edge: check-then-set race → lock. Edge: shared mutable object → return copy.

R8: RC `is None` only reloads when empty, staleness at load-once → reload on mtime/size. Falsifiable + REPRO steps. Symptom-patch TTL. Symptom-patch always-re-read (deletes feature). Symptom-patch manual clear_cache. Correct fix stat mtime+size. mtime granularity caveat. path ignored → key by resolved path. JSON null: content null → None → guard perpetually true, reloads every call → sentinel. Shared mutable return → copy/frozen. Concurrent check-then-set race → lock. Load failure propagates uncaught.

R9: RC `is None` true once per process, no mtime/hash stored → key cache on change signal (mtime/hash). Falsifiable statement + REPRO. TTL not-fix. Manual clear not-fix. Re-read-always not-fix (discards feature). path unkeyed global → key by resolved path. Shared mutable return → deep copy. Not thread-safe, two threads None + mtime race → lock. JSON null/empty leaves `is None` true → reloads every call → distinct sentinel; first-call open/json.load failure propagates. mtime coarse resolution caveat.

R10: RC populated once, no path re-reads/clears → invalidate on stat mtime. Symptom TTL. Symptom always-re-read (deletes feature). Symptom manual clear_cache. `is None` wrong sentinel: JSON null → None → never sticks, reloads every call. path ignored → key by (path,mtime). Shared mutable return → deep copy. No locking, concurrent load → lock. mtime granularity caveat. REPRO: call, rewrite, call, assert old (fails today); after fix new; unchanged file no re-read.

R11: RC cache populated once never invalidated, `is None` never re-checks → compare mtime/hash each call, reload on change (or remove cache). Tempting: "always reload" fixes staleness but disk read every call — pair with mtime. Tempting: TTL masks, edits missed/late. Tempting: manual clear only helps same-process editor, external edits missed. Not thread-safe, concurrent first-calls race → lock. path arg ignored → key by path.

R12: RC `is None` fires once per process lifetime, no re-read → invalidate on mtime/hash. TTL doesn't fix (shrinks window + race). Always re-read defeats caching. Manual reload doesn't auto-run. Restart/SIGHUP masks. Secondary: cache keyed by nothing, other path returns first file → key by mtime+content/path. Concurrent reload race (read mid-write) → lock.

R13: RC `is None` guards first load only, never re-validates → record mtime/hash, reload on change. TTL inadequate (stale within window). Manual invalidate() shifts burden to callers. Delete caching/always open+load defeats purpose. Move `_cache` global→instance = pure refactor. Reload-only-on-exception: silent content changes missed. Concurrency: no lock around reload, race → lock.

R14: RC `is None` read once per process lifetime, nothing ties cache to file state → validate mtime/hash each call. Manual clear caller-dependent (no). lru_cache same never-expiring (no). TTL masks, stale in window (no). "restart process" workaround (no). thread-local addresses visibility not staleness (no). Hazard: concurrent reload reads half-written config → lock + atomic writes.

R15: RC `_cache` reused forever, no invalidation tied to file → check mtime/hash, reload. path ignored → key by path. Tempting TTL narrows window only. Tempting remove `is None`/always reload defeats caching. Tempting instance-attr = encapsulation only. Tempting manual reload() = burden on callers. Edge: concurrent writers/partial writes read mid-write → atomic write + retry.

R16: RC `is None` never true again after first load → invalidate on mtime/hash each call. Tempting TTL masks. Tempting always re-read discards caching. Tempting manual clear fragile. path ignored → key by resolved path. Edge missing/invalid file (raise vs fallback undecided). Edge concurrent first calls double-parse → lock. Edge shared mutable return → copy/freeze. REPRO: call, edit, call, expect updated; after fix confirm + untouched file causes no re-parse.

R17: RC `is None` = "have we loaded" not "is current" → track mtime/hash, reload on differ. TTL non-fix. Always re-read non-fix (removes caching). Manual clear non-fix (relocates). Secondary: cache ignores path → key by resolved path. Edge missing file/invalid JSON, no recovery defined. Edge shared mutable return dict → deep copy/immutable. Edge no locking, concurrent reload race → lock. REPRO: call, edit, call, pre-fix stale; post-fix assert content matches edited file.

R18: RC `is None` distinguishes never-loaded vs loaded, no notion of file changed → track mtime/hash, reload. TTL non-fix. Always re-read deletes purpose. Manual clear relocates. Edge missing/invalid file: reload must not clobber good cache/crash. Edge concurrency: mutated with no lock, torn (mtime,data) → lock/atomic swap. Edge aliasing: returns dict by ref, caller mutation corrupts → copy. Edge mtime granularity, same-timestamp writes → mtime+size/hash. REPRO + regression test that fails on current code, passes after.

R19: RC `is None` never re-fires, nothing invalidates → check mtime/hash, reload. Symptom TTL reject. Symptom always re-read reject. Symptom manual clear reject. Real bug: path ignored once `_cache` set → key by path. Real bug: same dict returned every call, caller mutation corrupts → copy/frozen. Concurrency: check-then-load not locked; a reload-on-mtime fix must guard → lock. Edge: missing file/invalid JSON on first call leaves None (retries); a naive except caching {} would regress.

R20: RC `is None` permanent "loaded" flag, no invalidation signal → load on freshness check (mtime/hash) each call. Symptom TTL. Symptom always re-read removes caching. Concurrency: global mutable no lock, partial read/double read → lock/atomic swap. No error handling on open/json.load: missing/invalid leaves None forever, transient bad read clobbers good → only replace after successful parse. Shared mutable return → copy/immutable. Falsifiable cause + REPRO: call, edit, call, assert unchanged; re-verify after mtime/hash fix.
