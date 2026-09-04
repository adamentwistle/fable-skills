1. Cache never invalidates when source file changes on disk — check file modification time (mtime) on each call and reread if mtime changed since last cache.
2. Error handling won't help; file changes are silent, not I/O errors — must check mtime unconditionally, regardless of exception status.
3. TTL-based refresh is tempting but wrong—still stale between intervals — use actual file mtime comparison instead.
4. Removing the `global` keyword is tempting but wrong—doesn't change that cache persists — issue is persistence itself, not scope.