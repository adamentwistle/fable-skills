1. Module-level cache never invalidated once set — fix by checking file mtime/hash on each call and reloading when it changes.
2. `_cache is None` check means the cache lives for the process lifetime — fix by making staleness (not presence) the reload condition.
3. Tempting fix "just remove the cache and read the file every call" defeats the purpose of caching (perf) rather than addressing correctness — not a real fix, just an evasion.
4. Tempting fix "reduce cache lifetime with a timer/TTL" masks the bug with polling latency instead of detecting actual changes — still serves stale data between TTL windows.
5. Tempting fix "add a manual `invalidate_cache()` / `reload_config()` function" only helps if every caller remembers to call it — doesn't fix `get_config()` itself, so default usage stays broken.
6. Path parameter is ignored after first call (cache is keyed by nothing) — fix by keying the cache dict by resolved path, or reload check must still respect a differing `path` argument.