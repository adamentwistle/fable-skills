1. Cache populated once and never invalidated — root cause; fix by checking file mtime/hash each call and reloading when it changes.
2. `_cache is None` check means cache never expires — reload keyed on staleness, not existence.
3. Tempting fix "just remove the cache / read file every call" — works but defeats the purpose of caching; not addressing "why cache" if perf mattered.
4. Tempting fix "add a TTL that expires after N seconds" — does NOT properly fix it; file could change within the TTL window (stale reads persist) or not change at all (needless reloads).
5. Tempting fix "call get_config() again after editing config" — doesn't help; bug is in-process, caller has no way to force invalidation.
6. Tempting fix "make `_cache` non-global / instance attribute" — irrelevant; doesn't touch the staleness logic at all.
7. Multiple processes each hold their own `_cache` — fix above is per-process; if cross-process consistency is required, need a shared invalidation signal (e.g., file watch or version stamp in a shared store), not just mtime check.