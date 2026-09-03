1. Global `_cache` populated once and never invalidated — fix: check file mtime/hash each call and reload when it changes, or drop caching entirely.
2. Cache never expires, so no TTL fixes it either — fix: reload on every call, or tie invalidation to mtime, not time elapsed.
3. Tempting-but-wrong: adding `_cache = None` reset only fixes it until next edit — doesn't solve staleness, just delays it.
4. Tempting-but-wrong: reducing/adding a TTL cache "helps" but still serves stale data for up to the TTL window.
5. Tempting-but-wrong: making `_cache` a `dict` keyed by `path` doesn't help — still never re-reads a given path once cached.
6. Underlying issue: no file-change detection at all — correct fix is to store `(mtime, cache)` per path and reload when `os.path.getmtime(path)` changes.