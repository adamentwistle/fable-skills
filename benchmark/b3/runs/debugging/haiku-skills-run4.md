1. Root cause: cache never invalidates; set once on first call, always returned thereafter regardless of file changes.
2. Correct fix: check file modification time (mtime) on each call; re-read if mtime changed since caching.
3. Tempting but wrong: remove caching entirely — solves staleness but loses performance optimization.
4. Tempting but wrong: TTL-based expiration — doesn't detect actual file changes, just waits.
5. Tempting but wrong: add `force_refresh` parameter — shifts responsibility to callers who may not know when to call it.