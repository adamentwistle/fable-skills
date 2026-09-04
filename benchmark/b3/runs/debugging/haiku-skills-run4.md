1. **Root cause**: `_cache is None` check only triggers once; after that, the global variable is never re-evaluated against the file, so subsequent calls always return the first-loaded value regardless of disk changes — fix: implement a cache invalidation strategy based on file state.

2. **Tempting wrong fix (resetting cache to None)**: Setting `_cache = None` at function end defeats the entire purpose of caching and just re-reads the file on every call with no benefit.

3. **Tempting wrong fix (time-based TTL)**: Adding a "reload if older than N seconds" check still misses real config changes that happen between intervals and creates unpredictable stale-data windows.

4. **Tempting wrong fix (file size only)**: Checking whether file size changed doesn't catch changes that preserve byte count (e.g., content rearrangement, metadata changes, or single-byte value substitutions).

5. **Correct fix**: Check file modification time before returning cached value and reload if file has changed on disk — provides both caching efficiency and reliable change detection.