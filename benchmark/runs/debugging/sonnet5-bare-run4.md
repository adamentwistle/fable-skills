<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07). Agent run: s-dbg-bare-4. Content below the line is the agent's final output, unmodified. -->

---

1. Root cause: the `if _cache is None` guard means the file is read exactly once per process lifetime — there is no mechanism tying the cached value to the file's actual state, so any later edit is invisible → fix: validate the cache against the file each call (e.g., compare `os.path.getmtime(path)`/hash to a stored value and reload when it differs).
2. Tempting fix "clear `_cache` manually in a helper the caller must remember to invoke" would not fix it → still stale until someone remembers to call it; fix: make invalidation automatic, not caller-dependent.
3. Tempting fix "swap the global for `functools.lru_cache`" would not fix it → same unbounded, never-expiring cache, just relocated; fix: any caching layer still needs a staleness check keyed on the file.
4. Tempting fix "add a fixed TTL (e.g. reload every 60s)" would not fully fix it → masks the symptom but still serves stale data inside the window and reloads needlessly when the file hasn't changed; fix: use change-detection (mtime/hash), not a timer.
5. Tempting fix "just tell users to restart the process" is a process workaround, not a code fix → the bug report is precisely that this shouldn't be required; fix: make `get_config()` itself reload on change.
6. Tempting fix "make `_cache` per-thread (`threading.local`)" would not fix it → addresses cross-thread cache visibility, not staleness against disk; fix: unrelated axis, don't conflate.
7. Overlooked hazard once mtime-checking is added: concurrent calls during a reload can read a half-written config if writers don't write atomically → fix: guard reload with a lock and/or require atomic writes (write-tmp + rename) on the config-producing side.
