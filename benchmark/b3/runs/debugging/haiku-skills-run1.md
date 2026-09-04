1. Cache never invalidates after first read; track file modification time and reload when mtime changes.

2. Tempting but won't work—remove caching entirely: solves staleness but forces I/O on every call, defeating the caching purpose.

3. Tempting but won't work—reset cache on read errors: file modifications aren't errors, so the cache stays stale after a normal write.